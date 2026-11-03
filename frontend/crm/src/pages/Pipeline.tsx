import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { compactMoney, errorText, int, pct, relative } from "@xedu/shared/lib";
import {
  Badge,
  Button,
  Dialog,
  Field,
  IconButton,
  Menu,
  Segmented,
  Select,
  Switch,
  Textarea,
  useToast,
} from "@xedu/shared/ui";
import { MoreHorizontal } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { ActionKey, PipelineBoard, PipelineCard } from "../api/types";
import { useMe } from "../app/session";
import { Score, SimulatedTag } from "../components/lead-bits";
import { KpiStrip, PageHeader } from "../components/page";
import { Loading, LoadError } from "../components/state";
import { STAGE_LABEL } from "../lib/labels";
import { moneyLine } from "../lib/money";

const MOVABLE = ["Lead", "Engaged", "MQL", "SQL", "Lost"];

function useMove() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({
      card,
      stage,
      reason,
      note,
    }: {
      card: PipelineCard;
      stage: string | null;
      reason?: string;
      note?: string;
    }) =>
      stage === null
        ? api.del(`/pipeline/${card.user_id}`)
        : api.put(`/pipeline/${card.user_id}`, { stage, reason, note }),
    onSuccess: (_r, v) => {
      toast({
        tone: "good",
        text:
          v.stage === null
            ? `${v.card.name} follows their behaviour again.`
            : `${v.card.name} moved to ${STAGE_LABEL[v.stage] ?? v.stage}.`,
      });
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
      void qc.invalidateQueries({ queryKey: ["lead"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
}

/** Take the card's best step now (logged like an automatic decision, as "Take this step" on the lead page). */
function useAct() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ card, action }: { card: PipelineCard; action: ActionKey }) =>
      api.post<{ message: string }>(`/leads/${card.lead_id}/act`, { action }),
    onSuccess: (r, v) => {
      toast({ tone: "good", text: `${v.card.name}: ${r.message}` });
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
      void qc.invalidateQueries({ queryKey: ["lead"] });
      void qc.invalidateQueries({ queryKey: ["actions"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
}

function LostDialog({ card, reasons, onClose }: { card: PipelineCard; reasons: string[]; onClose: () => void }) {
  const move = useMove();
  const [reason, setReason] = useState(reasons[0] ?? "");
  const [note, setNote] = useState("");
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Move ${card.name} to Lost`}
      description="The CRM stops every automatic step for them until someone re-opens the lead."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="danger"
            loading={move.isPending}
            onClick={() => move.mutate({ card, stage: "Lost", reason, note }, { onSuccess: onClose })}
          >
            Move to Lost
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Reason">
          <Select
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            options={reasons.map((r) => ({ value: r, label: r }))}
          />
        </Field>
        <Field label="Note" optional>
          <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
        </Field>
      </div>
    </Dialog>
  );
}

function Card({ card, reasons }: { card: PipelineCard; reasons: string[] }) {
  const move = useMove();
  const act = useAct();
  const [losing, setLosing] = useState(false);
  const isCustomer = card.stage === "Customer";
  const isOpen = !isCustomer && card.stage !== "Lost";
  const line = moneyLine(card);
  const items = isCustomer
    ? []
    : [
        ...MOVABLE.filter((s) => s !== card.stage).map((s) => ({
          label: `Move to ${STAGE_LABEL[s] ?? s}`,
          onSelect: () => (s === "Lost" ? setLosing(true) : move.mutate({ card, stage: s })),
        })),
        ...(card.moved_by_hand
          ? [
              {
                label: "Back to automatic",
                hint: `Stage from their behaviour: ${STAGE_LABEL[card.auto_stage] ?? card.auto_stage}`,
                onSelect: () => move.mutate({ card, stage: null }),
              },
            ]
          : []),
      ];
  return (
    <li className="rounded-md border border-line bg-surface p-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <Link
            to={`/leads/${card.lead_id}`}
            className="block truncate text-[13.5px] font-medium text-ink hover:text-brand-ink hover:underline"
          >
            {card.name}
          </Link>
          <p className="truncate text-[12.5px] text-muted">{card.course ?? "No course chosen"}</p>
        </div>
        {items.length > 0 && (
          <Menu
            label={`Move ${card.name}`}
            items={items}
            trigger={(p) => (
              <IconButton {...p} label={`Move ${card.name}`} size="sm" className="-mr-1.5 -mt-1">
                <MoreHorizontal aria-hidden className="size-4" />
              </IconButton>
            )}
          />
        )}
      </div>
      <div className="mt-2 flex items-center gap-3 text-[12.5px]">
        <Score score={card.score} tier={isCustomer ? null : card.tier} />
        {isOpen && card.p_anyway !== null && (
          <span className="num ml-auto text-ink-2" title="Chance of buying within 14 days if the team does nothing">
            {pct(card.p_anyway)} chance
          </span>
        )}
      </div>
      {isOpen && line.action && (
        <div className="mt-2 flex items-center gap-2 rounded-md bg-good-soft px-2.5 py-1.5">
          <p className="min-w-0 flex-1 text-[12.5px] text-ink">
            {line.pWithout !== null && line.pWith !== null && (
              <>
                <span className="num font-semibold">
                  {pct(line.pWithout)} → {pct(line.pWith)}
                </span>{" "}
              </>
            )}
            <span className="text-ink-2">{line.text}</span>
          </p>
          <Button
            size="sm"
            variant="primary"
            loading={act.isPending}
            onClick={() => line.action && act.mutate({ card, action: line.action })}
            aria-label={`Take the step for ${card.name}`}
          >
            Do it
          </Button>
        </div>
      )}
      {isOpen && !line.action && line.text && <p className="mt-2 text-[12px] text-muted">{line.text}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
        <span className="mr-auto">{card.owner}</span>
        {card.last_seen && <span>Seen {relative(card.last_seen)}</span>}
      </div>
      {(card.simulated || card.moved_by_hand || card.control_group || card.lost_reason || card.no_discount) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {isOpen && card.no_discount && (
            <Badge
              tone="info"
              title="More likely than not to buy without help, and a coupon would hardly change that: no discount is given"
            >
              No discount needed
            </Badge>
          )}
          {card.moved_by_hand && (
            <Badge tone="info" title={card.moved_by ? `Moved by ${card.moved_by}` : undefined}>
              Moved by hand
            </Badge>
          )}
          {card.lost_reason && <Badge>{card.lost_reason}</Badge>}
          {card.control_group && <Badge variant="outline">Control group</Badge>}
          {card.simulated && <SimulatedTag />}
        </div>
      )}
      {losing && <LostDialog card={card} reasons={reasons} onClose={() => setLosing(false)} />}
    </li>
  );
}

export default function Pipeline() {
  const me = useMe();
  const [params, setParams] = useSearchParams();
  const owner = params.get("owner") ?? (me.role === "counsellor" ? "me" : "all");
  const simulated = params.get("simulated") !== "no";
  const sort = params.get("sort") === "score" ? "score" : "money";
  const set = (k: string, v: string | null) =>
    setParams(
      (p) => {
        if (v === null) p.delete(k);
        else p.set(k, v);
        return p;
      },
      { replace: true },
    );
  const board = useQuery({
    queryKey: ["pipeline", owner, simulated, sort],
    queryFn: () => api.get<PipelineBoard>("/pipeline", { owner, include_simulated: simulated, limit: 40, sort }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  return (
    <>
      <PageHeader
        title="Pipeline"
        description="Every open lead in its stage, in rupees: what will come in anyway if the team does nothing, and what the team can still add with the best step now. Stages follow what people do on the website; move a lead by hand when you know better."
      />
      {board.data && (
        <KpiStrip
          className="mb-5"
          items={[
            {
              label: "Comes in anyway",
              value: compactMoney(board.data.totals.anyway),
              detail: `next ${board.data.totals.window_days} days, if the team does nothing`,
            },
            {
              label: "The team can add",
              value: compactMoney(board.data.totals.add),
              detail: `with the best step for ${int(board.data.totals.work)} leads`,
            },
            {
              label: "No discount needed",
              value: int(board.data.totals.no_discount),
              detail: "likely buyers who need no discount",
            },
            {
              label: "Open leads",
              value: int(board.data.totals.open_leads),
              detail: owner === "me" ? "yours" : owner === "unassigned" ? "nobody's yet" : "everyone's",
            },
          ]}
        />
      )}
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <Segmented
          label="Whose leads"
          value={owner}
          onChange={(v) => set("owner", v)}
          options={[
            { value: "me", label: "Mine" },
            { value: "unassigned", label: "Unassigned" },
            { value: "all", label: "Everyone's" },
          ]}
        />
        <Segmented
          label="Order"
          value={sort}
          onChange={(v) => set("sort", v === "money" ? null : v)}
          options={[
            { value: "money", label: "Work first" },
            { value: "score", label: "Highest score" },
          ]}
        />
        <div className="w-64">
          <Switch
            checked={simulated}
            onChange={(v) => set("simulated", v ? null : "no")}
            label="Include simulated learners"
          />
        </div>
      </div>
      {board.isPending ? (
        <Loading label="Loading the board" />
      ) : board.isError ? (
        <LoadError error={board.error} what="the pipeline" retry={() => void board.refetch()} />
      ) : (
        <div className="-mx-4 overflow-x-auto px-4 pb-2 sm:-mx-6 sm:px-6">
          <div className="flex min-w-max gap-4">
            {board.data.columns.map((col) => (
              <section key={col.stage} aria-label={STAGE_LABEL[col.stage] ?? col.stage} className="w-[272px] shrink-0">
                <header className="mb-2.5 border-b-2 border-line-strong pb-2">
                  <div className="flex items-baseline gap-2">
                    <h2 className="text-[14px] font-semibold text-ink">{STAGE_LABEL[col.stage] ?? col.stage}</h2>
                    <span className="num text-[13px] text-muted">{int(col.count)}</span>
                  </div>
                  {col.stage !== "Customer" && col.stage !== "Lost" && (
                    <p className="num mt-0.5 text-[12.5px] text-muted">
                      <span title="Comes in anyway if the team does nothing">{compactMoney(col.anyway)} anyway</span>
                      {col.add > 0 && (
                        <span className="text-good" title="What the team can add with the best step now">
                          {" "}
                          · +{compactMoney(col.add)} to add
                        </span>
                      )}
                    </p>
                  )}
                  {col.about && <p className="mt-0.5 text-[12px] text-muted">{col.about}</p>}
                </header>
                {col.cards.length === 0 ? (
                  <p className="rounded-md border border-dashed border-line px-3 py-6 text-center text-[12.5px] text-muted">
                    No leads here
                  </p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {col.cards.map((c) => (
                      <Card key={c.user_id} card={c} reasons={board.data.lost_reasons} />
                    ))}
                  </ul>
                )}
                {col.count > col.cards.length && (
                  <p className="mt-2 text-center text-[12.5px] text-muted">
                    Showing {col.cards.length} of {int(col.count)},{" "}
                    {sort === "money" ? "where a step helps most" : "highest scores"} first.{" "}
                    <Link className="text-brand-ink hover:underline" to="/leads">
                      All leads
                    </Link>
                  </p>
                )}
              </section>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
