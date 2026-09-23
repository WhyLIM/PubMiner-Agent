"use client";

/**
 * Agent Workspace（PR-012 最小版）。
 *
 * 布局遵循设计文档 §11.1：左侧会话（目标/澄清/结论），中间计划与行动，
 * 右侧证据定位（点击 candidate claim 跳到高亮原文 span）。
 * 数据全部来自 /api/v1 typed client；行动事件用 SSE 订阅 + 游标恢复。
 */
import { useEffect, useRef, useState } from "react";

import { agentApi, type EvidenceSpanItem } from "@/shared/api/agent-client";
import { subscribeSessionEvents, type EventSubscription } from "@/shared/api/sse";
import { useAgentWorkspace } from "@/features/agent/store";

export default function AgentWorkspacePage() {
  const store = useAgentWorkspace();
  const subscriptionRef = useRef<EventSubscription | null>(null);
  const [answerDraft, setAnswerDraft] = useState("");
  const [selectedClaim, setSelectedClaim] = useState<string | null>(null);
  const [spans, setSpans] = useState<EvidenceSpanItem[]>([]);

  // SSE：会话存在即订阅；组件卸载关闭
  useEffect(() => {
    subscriptionRef.current?.close();
    if (!store.sessionId) return;
    const subscription = subscribeSessionEvents(
      store.sessionId,
      (events) => store.appendEvents(events),
      () => store.setError("行动事件流中断，正在用游标补齐…"),
    );
    subscriptionRef.current = subscription;
    return () => subscription.close();
  }, [store.sessionId]);

  const openClaim = async (claimId: string) => {
    setSelectedClaim(claimId);
    try {
      const evidence = await agentApi.getClaimEvidence(claimId);
      setSpans(evidence.evidence ?? []);
    } catch {
      store.setError("无法加载证据原文");
    }
  };

  return (
    <div className="mx-auto grid max-w-7xl grid-cols-1 gap-4 p-6 lg:grid-cols-3">
      {/* 左：会话 */}
      <section className="space-y-4 rounded-xl border p-4">
        <h1 className="text-lg font-semibold">PubMiner Evidence Agent</h1>
        <textarea
          className="h-24 w-full rounded-lg border p-2 text-sm"
          placeholder="用自然语言描述研究目标，例如：寻找 2020 年以来胰腺癌预后 biomarker，并确认是否存在独立队列验证"
          value={store.goalDraft}
          onChange={(event) => store.setGoalDraft(event.target.value)}
        />
        <button
          className="w-full rounded-lg bg-black px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
          disabled={store.phase !== "idle" || !store.goalDraft.trim()}
          onClick={() => void store.createSession()}
        >
          创建研究会话
        </button>

        {store.error && (
          <p className="rounded-lg bg-red-50 p-2 text-xs text-red-700">{store.error}</p>
        )}

        {store.session && (
          <div className="space-y-2 text-xs">
            <p>
              会话 <code className="rounded bg-gray-100 px-1">{store.sessionId}</code> · 状态
              <span className="ml-1 font-semibold">{store.session.status}</span> · 第{" "}
              {store.session.turn} 轮
            </p>
            {store.session.stop_reason != null && (
              <p className="rounded bg-amber-50 p-2">
                停止原因：{String(store.session.stop_reason.kind)} —{" "}
                {String(store.session.stop_reason.message ?? "")}
              </p>
            )}
            <div className="space-y-1">
              <label className="block font-medium">澄清：疾病（disease）</label>
              <input
                className="w-full rounded border p-1"
                placeholder="如 PDAC"
                value={store.diseaseDraft}
                onChange={(event) => store.setDiseaseDraft(event.target.value)}
              />
              <button
                className="w-full rounded border px-2 py-1 disabled:opacity-40"
                disabled={!store.diseaseDraft.trim()}
                onClick={() => void store.confirmTaskSpec()}
              >
                确认约束（绑定 TaskSpec）
              </button>
            </div>
            <div className="space-y-1">
              <label className="block font-medium">追问 / 补充说明</label>
              <textarea
                className="h-16 w-full rounded border p-1"
                value={answerDraft}
                onChange={(event) => setAnswerDraft(event.target.value)}
              />
              <button
                className="w-full rounded border px-2 py-1 disabled:opacity-40"
                disabled={!answerDraft.trim()}
                onClick={() => {
                  void store.answerClarification(answerDraft);
                  setAnswerDraft("");
                }}
              >
                发送给 Agent
              </button>
            </div>
          </div>
        )}
      </section>

      {/* 中：计划与行动 */}
      <section className="space-y-4 rounded-xl border p-4">
        <h2 className="text-base font-semibold">研究计划与行动</h2>
        {store.session && (
          <>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded border px-2 py-1 text-xs disabled:opacity-40"
                disabled={store.phase === "running"}
                onClick={() => void store.submitAndApprovePlan()}
              >
                生成并批准计划
              </button>
              <button
                className="rounded border px-2 py-1 text-xs disabled:opacity-40"
                disabled={store.phase !== "planning"}
                onClick={() => void store.runMiningTask()}
              >
                执行检索任务
              </button>
              <button
                className="rounded border px-2 py-1 text-xs"
                onClick={() => void store.pauseSession()}
              >
                暂停
              </button>
            </div>

            <div>
              <h3 className="mb-1 text-sm font-medium">计划版本</h3>
              {(store.session.plans ?? []).map((plan) => (
                <div key={plan.version} className="mb-1 rounded bg-gray-50 p-2 text-xs">
                  v{plan.version} {plan.approved_by_human ? "（已批准）" : "（待批准）"} ·{" "}
                  {plan.rationale}
                </div>
              ))}
            </div>

            <div>
              <h3 className="mb-1 text-sm font-medium">行动轨迹（真实 tool/workflow 事件）</h3>
              <ul className="max-h-64 space-y-1 overflow-y-auto text-xs">
                {store.events.map((event) => (
                  <li key={event.seq} className="rounded bg-gray-50 p-2">
                    <span className="font-mono">#{event.seq}</span> [{event.action_type}]
                    {event.tool_name ? ` ${event.tool_name}` : ""} — {event.status}
                    {event.summary ? `：${event.summary}` : ""}
                  </li>
                ))}
                {store.events.length === 0 && <li className="text-gray-500">暂无行动</li>}
              </ul>
            </div>
          </>
        )}
        {!store.session && <p className="text-xs text-gray-500">先在左侧创建研究会话。</p>}
      </section>

      {/* 右：结论与证据定位 */}
      <section className="space-y-4 rounded-xl border p-4">
        <h2 className="text-base font-semibold">Candidate Claims 与证据</h2>
        <button
          className="w-full rounded border px-2 py-1 text-xs"
          onClick={() => void store.refreshClaims()}
        >
          刷新 claims
        </button>
        <ul className="space-y-1 text-xs">
          {store.claims.map((claim) => (
            <li key={claim.claim_id}>
              <button
                className={`w-full rounded border p-2 text-left ${
                  selectedClaim === claim.claim_id ? "border-black" : ""
                }`}
                onClick={() => void openClaim(claim.claim_id)}
              >
                <span className="font-mono text-[10px]">{claim.canonical_signature}</span>
                <span className="ml-1">
                  [{claim.status}] 支持 {claim.polarities?.SUPPORT ?? 0} / 反对{" "}
                  {claim.polarities?.CONTRADICT ?? 0} / 无效应 {claim.polarities?.NO_EFFECT ?? 0}
                </span>
              </button>
            </li>
          ))}
          {store.claims.length === 0 && <li className="text-gray-500">尚无 candidate claim</li>}
        </ul>

        {spans.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium">原文证据（固定 offset 定位）</h3>
            {spans.map((item) => {
              const canonical = item.canonical_text ?? "";
              const before = canonical.slice(0, item.span.start_char);
              const highlighted = canonical.slice(item.span.start_char, item.span.end_char);
              const after = canonical.slice(item.span.end_char);
              return (
                <div key={item.evidence_id} className="rounded bg-yellow-50 p-2 text-xs leading-5">
                  <p className="mb-1 text-gray-500">
                    {item.document_title || "（无标题）"} · {item.span.section_path} ·{" "}
                    {item.polarity}
                  </p>
                  <p>
                    {before}
                    <mark className="bg-yellow-300">{highlighted}</mark>
                    {after}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
