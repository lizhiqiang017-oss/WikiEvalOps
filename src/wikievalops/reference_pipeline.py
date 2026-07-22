from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from .contracts import (
    ClaimTrace,
    ContextItem,
    ContextTrace,
    EvalCase,
    EvaluationTrace,
    GenerationTrace,
    RetrievedDocument,
    RetrievalTrace,
    RouteTrace,
    UsageTrace,
)


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    content: str
    keywords: tuple[str, ...]


TECHNICAL_KNOWLEDGE = (
    KnowledgeDocument(
        "fact:repo-api",
        "repository.py 实现了 RepositoryAPI，负责仓储接口的数据访问。",
        ("仓储接口", "repository", "实现"),
    ),
    KnowledgeDocument(
        "fact:service-storage-edge",
        "service.py 导入并调用 StorageClient。",
        ("服务模块", "服务层", "存储客户端", "StorageClient", "存储依赖"),
    ),
    KnowledgeDocument(
        "fact:storage-database-edge",
        "StorageClient 将数据写入数据库。",
        ("持久化", "数据库", "写入", "调用路径"),
    ),
    KnowledgeDocument(
        "fact:unrelated",
        "controller.py 负责接收请求，不直接访问存储。",
        ("控制器", "请求"),
    ),
    KnowledgeDocument(
        "file:after-sale-policy",
        "售后政策文件规定：签收后 7 天内可申请无理由退货，超期需走人工审核。",
        ("售后政策", "文件", "退货", "人工审核", "File Wiki"),
    ),
    KnowledgeDocument(
        "system:ticket-risk-flow",
        "客服工单系统由 intake、risk_filter、manual_review 三个节点组成，高风险工单必须进入人工复核。",
        ("工单系统", "风险过滤", "人工复核", "System Wiki", "链路"),
    ),
    KnowledgeDocument(
        "system:provider-score-flow",
        "服务商评分链路汇总投诉率、首次解决率、平均响应时间，并输出低/中/高三级风险。",
        ("服务商评分", "投诉率", "首次解决率", "平均响应时间", "System Wiki"),
    ),
)


class ReferencePipeline:
    """用于可复现实验的轻量被测系统，不依赖评测 Gold Label。"""

    def __init__(self, version: str) -> None:
        if version not in {"reference-v1", "reference-v2"}:
            raise ValueError(f"不支持的 ReferencePipeline 版本：{version}")
        self.version = version

    def execute(self, case: EvalCase) -> EvaluationTrace:
        """只读取样本输入并产生 Trace，禁止使用 expected 字段。"""

        started = perf_counter()
        query = case.input.query
        routes = self._route(query)
        documents = self._retrieve(query, routes, case.input.business_data)
        context_items = [
            ContextItem(evidence_id=document.document_id, content=document.content)
            for document in documents
        ]
        generation = self._generate(query, routes, documents, case.input.business_data)
        elapsed_ms = (perf_counter() - started) * 1000
        return EvaluationTrace(
            case_id=case.case_id,
            system_version=self.version,
            route=RouteTrace(
                selected=routes,
                candidates=["technical_qa", "commerce_risk", "fact_wiki", "file_wiki", "system_wiki"],
            ),
            retrieval=RetrievalTrace(documents=documents),
            context=ContextTrace(items=context_items, token_count=sum(len(item.content) for item in context_items)),
            generation=generation,
            usage=UsageTrace(retrieval_call_count=1),
            timing_ms={"total": elapsed_ms},
        )

    def _route(self, query: str) -> list[str]:
        commerce_hit = any(word in query for word in ("风险", "满意度", "服务商", "投诉率"))
        fact_wiki_hit = any(word in query for word in ("Fact Wiki", "事实 Wiki", "事实库"))
        file_wiki_hit = any(word in query for word in ("File Wiki", "文件 Wiki", "政策文件", "售后政策"))
        system_wiki_hit = any(word in query for word in ("System Wiki", "系统 Wiki", "工单系统", "评分链路"))
        technical_hit = any(word in query for word in ("接口", "模块", "调用", "依赖", "实现", "存储", "路径"))
        if self.version == "reference-v1":
            # v1 只选择第一个命中的意图，因此会遗漏跨业务、技术的多意图问题。
            if fact_wiki_hit:
                return ["fact_wiki"]
            if file_wiki_hit:
                return ["file_wiki"]
            if system_wiki_hit:
                return ["system_wiki"]
            if commerce_hit:
                return ["commerce_risk"]
            return ["technical_qa"] if technical_hit else []
        routes = []
        wiki_hit = fact_wiki_hit or file_wiki_hit or system_wiki_hit
        if commerce_hit and not wiki_hit:
            routes.append("commerce_risk")
        if fact_wiki_hit:
            routes.append("fact_wiki")
        if file_wiki_hit:
            routes.append("file_wiki")
        if system_wiki_hit:
            routes.append("system_wiki")
        if technical_hit and not {"fact_wiki", "file_wiki", "system_wiki"} & set(routes):
            routes.append("technical_qa")
        return routes

    def _retrieve(self, query: str, routes: list[str], business_data: dict) -> list[RetrievedDocument]:
        documents: list[RetrievedDocument] = []
        knowledge_routes = {"technical_qa", "fact_wiki", "file_wiki", "system_wiki"}
        if knowledge_routes & set(routes):
            matched = []
            for document in TECHNICAL_KNOWLEDGE:
                score = sum(keyword in query for keyword in document.keywords)
                if score:
                    matched.append((score, document))
            if self.version == "reference-v1" and "哪个模块调用" in query:
                matched = [(1, TECHNICAL_KNOWLEDGE[-1])]
            matched.sort(key=lambda row: (-row[0], row[1].document_id))
            documents.extend(
                RetrievedDocument(
                    document_id=document.document_id,
                    content=document.content,
                    source="public-demo-repo",
                    score=min(1.0, score / 2),
                )
                for score, document in matched[:5]
            )

        if "commerce_risk" in routes and business_data:
            metric_map = {
                "complaint_rate": ("metric:complaint-rate", "投诉率"),
                "first_resolution_rate": ("metric:first-resolution", "首次解决率"),
                "avg_response_seconds": ("metric:response-time", "平均响应时间"),
            }
            for field, (document_id, label) in metric_map.items():
                if field in business_data:
                    documents.append(
                        RetrievedDocument(
                            document_id=document_id,
                            content=f"{label}={business_data[field]}",
                            source="synthetic-commerce-data",
                            score=1.0,
                        )
                    )
        # 同一证据只保留一次，模拟真实 Context 去重。
        return list({document.document_id: document for document in documents}.values())

    def _generate(
        self,
        query: str,
        routes: list[str],
        documents: list[RetrievedDocument],
        business_data: dict,
    ) -> GenerationTrace:
        if "commerce_risk" in routes and business_data:
            return self._generate_risk(business_data)
        if {"fact_wiki", "file_wiki", "system_wiki"} & set(routes):
            return self._generate_wiki(routes, documents)
        return self._generate_technical(query, documents)

    def _generate_technical(self, query: str, documents: list[RetrievedDocument]) -> GenerationTrace:
        ids = {document.document_id for document in documents}
        claims: list[ClaimTrace] = []
        if "fact:repo-api" in ids:
            claims.append(ClaimTrace(claim_id="repo-api", text="仓储接口实现在 repository.py 中", evidence_ids=["fact:repo-api"]))
        if "fact:service-storage-edge" in ids:
            claims.append(ClaimTrace(claim_id="service-storage", text="服务模块调用存储客户端", evidence_ids=["fact:service-storage-edge"]))
        if "fact:storage-database-edge" in ids:
            claims.append(ClaimTrace(claim_id="storage-db", text="存储客户端写入数据库", evidence_ids=["fact:storage-database-edge"]))
        if not claims and self.version == "reference-v1":
            claims.append(ClaimTrace(claim_id="guess", text="控制器调用存储模块", evidence_ids=[]))
        answer = "；".join(claim.text for claim in claims) if claims else "当前证据不足，无法回答。"
        return GenerationTrace(answer=answer, claims=claims, citations=[evidence for claim in claims for evidence in claim.evidence_ids])

    def _generate_wiki(self, routes: list[str], documents: list[RetrievedDocument]) -> GenerationTrace:
        ids = {document.document_id for document in documents}
        claims: list[ClaimTrace] = []
        structured_output: dict[str, object] = {}

        if "fact_wiki" in routes and "fact:repo-api" in ids:
            claims.append(ClaimTrace(claim_id="fact-summary", text="仓储接口事实来自 repository.py", evidence_ids=["fact:repo-api"]))
            structured_output.update(
                {
                    "facts": ["RepositoryAPI 负责仓储接口的数据访问"],
                    "entities": ["RepositoryAPI", "repository.py"],
                    "source_evidence_ids": ["fact:repo-api"],
                }
            )
        if "file_wiki" in routes and "file:after-sale-policy" in ids:
            evidence_ids = ["file:after-sale-policy"] if self.version == "reference-v2" else ["file:missing-policy"]
            claims.append(ClaimTrace(claim_id="file-policy", text="7 天内可申请无理由退货", evidence_ids=evidence_ids))
            structured_output.update(
                {
                    "summary": "售后政策覆盖 7 天无理由退货和超期人工审核。",
                    "effective_rules": ["签收后 7 天内可申请无理由退货", "超期需人工审核"],
                    "source_evidence_ids": evidence_ids,
                }
            )
        if "system_wiki" in routes and "system:ticket-risk-flow" in ids:
            claims.append(ClaimTrace(claim_id="system-flow", text="高风险工单必须进入人工复核", evidence_ids=["system:ticket-risk-flow"]))
            structured_output.update(
                {
                    "nodes": ["intake", "risk_filter", "manual_review"],
                    "edges": [["intake", "risk_filter"], ["risk_filter", "manual_review"]],
                    "risk_controls": ["高风险工单进入人工复核"],
                    "source_evidence_ids": ["system:ticket-risk-flow"],
                }
            )

        if self.version == "reference-v1":
            structured_output.pop("source_evidence_ids", None)
        answer = "；".join(claim.text for claim in claims) if claims else "当前证据不足，无法生成 Wiki。"
        return GenerationTrace(
            answer=answer,
            claims=claims,
            citations=[evidence for claim in claims for evidence in claim.evidence_ids],
            structured_output=structured_output,
        )

    def _generate_risk(self, data: dict) -> GenerationTrace:
        complaint = float(data.get("complaint_rate", 0))
        resolution = float(data.get("first_resolution_rate", 1))
        response = float(data.get("avg_response_seconds", 0))

        if self.version == "reference-v1":
            risk_label = "high" if complaint >= 0.18 else "medium" if complaint >= 0.05 else "low"
        else:
            high_signals = sum((complaint >= 0.15, resolution <= 0.60, response >= 70))
            risk_label = "high" if high_signals >= 2 else "medium" if complaint >= 0.05 or resolution < 0.80 or response > 40 else "low"

        claims = [
            ClaimTrace(
                claim_id="complaint",
                text="投诉率偏高" if complaint >= 0.15 else "投诉率较低" if complaint < 0.03 else "投诉率需要关注",
                evidence_ids=["metric:complaint-rate"],
            ),
            ClaimTrace(
                claim_id="resolution",
                text="首次解决率偏低" if resolution <= 0.60 else "首次解决率表现健康" if resolution >= 0.85 else "首次解决率需要关注",
                evidence_ids=["metric:first-resolution"],
            ),
        ]
        if self.version == "reference-v2":
            claims.append(
                ClaimTrace(
                    claim_id="response",
                    text="响应时间过长" if response >= 70 else "响应时间正常",
                    evidence_ids=["metric:response-time"],
                )
            )
        return GenerationTrace(
            answer=f"综合判断为{risk_label}风险。" + "；".join(claim.text for claim in claims),
            risk_label=risk_label,
            claims=claims,
            citations=[evidence for claim in claims for evidence in claim.evidence_ids],
        )
