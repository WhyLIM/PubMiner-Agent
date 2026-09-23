"use client";

/**
 * Review UI（PR-013）。
 *
 * 双栏布局（设计文档 §11.3）：
 * - 左：Document viewer——保存的 canonical text，evidence span 高亮；
 * - 右：Claim 编辑器——signature、极性聚合、方向/结论修订、审核操作。
 * 底部操作仅 Accept / Edit and Accept / Reject / Needs Review，
 * 全部要求可追溯 reason；乐观锁版本号防并发覆盖。
 */
import { useCallback, useEffect, useState } from "react";

import {
  agentApi,
  type EvidenceSpanItem,
  type ReviewQueueItem,
} from "@/shared/api/agent-client";

type Decision = "ACCEPT" | "EDIT_ACCEPT" | "REJECT" | "NEEDS_REVIEW";

export default function ReviewPage() {
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [selected, setSelected] = useState<ReviewQueueItem | null>(null);
  const [spans, setSpans] = useState<EvidenceSpanItem[]>([]);
  const [revision, setRevision] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const refreshQueue = useCallback(async () => {
    try {
      const { items } = await agentApi.getReviewQueue();
      setQueue(items);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    agentApi
      .getReviewQueue()
      .then(({ items }) => {
        if (!cancelled) setQueue(items);
      })
      .catch((error) => {
        if (!cancelled) setMessage(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const openClaim = useCallback(
    async (item: ReviewQueueItem) => {
      setSelected(item);
      setSpans([]);
      try {
        const evidence = await agentApi.getClaimEvidence(item.claim_id);
        setSpans(evidence.evidence ?? []);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : String(error));
      }
    },
    [],
  );

  const submitDecision = useCallback(
    async (decision: Decision) => {
      if (!selected) return;
      if (!reason.trim()) {
        setMessage("审核必须填写 reason（可追溯性要求）");
        return;
      }
      try {
        const result = await agentApi.submitReviewDecision({
          claim_id: selected.claim_id,
          decision,
          reviewer_id: "curator",
          reason,
          expected_version: 1, // 队列项为 CANDIDATE v1；冲突时后端返回 409
          revision:
            decision === "EDIT_ACCEPT" && revision.trim()
              ? { direction: revision.trim().toUpperCase() }
              : {},
        });
        setMessage(`已提交 ${decision}：claim 现为 ${result.claim_status}（v${result.claim_version}）`);
        setReason("");
        setRevision("");
        await refreshQueue();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : String(error));
      }
    },
    [selected, reason, revision, refreshQueue],
  );

  const priorityColor = (priority: string) =>
    priority === "conflict"
      ? "bg-red-50 text-red-700"
      : priority === "needs_review"
        ? "bg-amber-50 text-amber-700"
        : "bg-gray-50";

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Review Queue</h1>
        <button
          className="rounded border px-2 py-1 text-xs"
          onClick={() => void refreshQueue()}
        >
          刷新队列
        </button>
      </div>
      {message && <p className="rounded bg-blue-50 p-2 text-xs">{message}</p>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 左：Document viewer */}
        <section className="space-y-3 rounded-xl border p-4">
          <h2 className="text-sm font-semibold">原文与证据定位</h2>
          {!selected && <p className="text-xs text-gray-500">从右侧选择一个待审 claim。</p>}
          {spans.length === 0 && selected && (
            <p className="text-xs text-gray-500">该 claim 暂无已存储的 evidence span。</p>
          )}
          {spans.map((item) => {
            const canonical = item.canonical_text ?? "";
            const before = canonical.slice(0, item.span.start_char);
            const highlighted = canonical.slice(item.span.start_char, item.span.end_char);
            const after = canonical.slice(item.span.end_char);
            return (
              <div key={item.evidence_id} className="rounded bg-white p-3 text-xs leading-5 ring-1 ring-gray-100">
                <p className="mb-1 text-gray-500">
                  {item.document_title || "（无标题）"} · {item.span.section_path} ·{" "}
                  <span
                    className={
                      item.polarity === "CONTRADICT"
                        ? "font-semibold text-red-600"
                        : item.polarity === "NO_EFFECT"
                          ? "font-semibold text-gray-600"
                          : "font-semibold text-green-700"
                    }
                  >
                    {item.polarity}
                  </span>
                </p>
                <p>
                  {before}
                  <mark className="bg-yellow-200">{highlighted}</mark>
                  {after}
                </p>
              </div>
            );
          })}
        </section>

        {/* 右：队列 + Claim editor */}
        <section className="space-y-4">
          <div className="space-y-2 rounded-xl border p-4">
            <h2 className="text-sm font-semibold">待审队列</h2>
            <ul className="space-y-1 text-xs">
              {queue.map((item) => (
                <li key={item.claim_id}>
                  <button
                    className={`w-full rounded border p-2 text-left ${
                      selected?.claim_id === item.claim_id ? "border-black" : ""
                    }`}
                    onClick={() => void openClaim(item)}
                  >
                    <span className={`mr-1 rounded px-1 ${priorityColor(item.priority)}`}>
                      {item.priority}
                    </span>
                    <span className="font-mono text-[10px]">{item.canonical_signature}</span>
                    <span className="ml-1">
                      支持 {item.polarities?.SUPPORT ?? 0} / 反对 {item.polarities?.CONTRADICT ?? 0}
                      {" "}
                      / 无效应 {item.polarities?.NO_EFFECT ?? 0}
                    </span>
                    {(item.reasons?.length ?? 0) > 0 && (
                      <span className="block text-gray-500">{(item.reasons ?? []).join("；")}</span>
                    )}
                  </button>
                </li>
              ))}
              {queue.length === 0 && <li className="text-gray-500">队列为空</li>}
            </ul>
          </div>

          {selected && (
            <div className="space-y-2 rounded-xl border p-4 text-xs">
              <h2 className="text-sm font-semibold">Claim Editor</h2>
              <p className="font-mono text-[10px]">{selected.canonical_signature}</p>
              <label className="block font-medium">修订 direction（仅 Edit and Accept 时生效）</label>
              <input
                className="w-full rounded border p-1"
                placeholder="HIGH / LOW / UNSPECIFIED"
                value={revision}
                onChange={(event) => setRevision(event.target.value)}
              />
              <label className="block font-medium">审核 reason（必填）</label>
              <textarea
                className="h-16 w-full rounded border p-1"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <div className="grid grid-cols-2 gap-2">
                <button
                  className="rounded border px-2 py-1"
                  onClick={() => void submitDecision("ACCEPT")}
                >
                  Accept
                </button>
                <button
                  className="rounded border px-2 py-1"
                  onClick={() => void submitDecision("EDIT_ACCEPT")}
                >
                  Edit and Accept
                </button>
                <button
                  className="rounded border px-2 py-1"
                  onClick={() => void submitDecision("REJECT")}
                >
                  Reject
                </button>
                <button
                  className="rounded border px-2 py-1"
                  onClick={() => void submitDecision("NEEDS_REVIEW")}
                >
                  Needs Review
                </button>
              </div>
              <p className="text-gray-400">
                Agent 只能产生 CANDIDATE；APPROVED/PUBLISHED 需要更高角色权限（发布门禁）。
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
