import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, Field, Input, Notice, Select, useToast } from "@xedu/shared/ui";
import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router";
import { api } from "../api/client";
import { useMe } from "../app/session";
import { AuthFrame } from "../components/AuthFrame";
import { OCCUPATION_LABEL, type ProfileOptions as Options } from "../lib/profile";

export default function Welcome() {
  const me = useMe();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const p = me.profile;
  const options = useQuery({
    queryKey: ["profile-options"],
    queryFn: () => api.get<Options>("/profile/options"),
    staleTime: Infinity,
  });
  const [occupation, setOccupation] = useState(
    p?.current_occupation && p.current_occupation !== "Unknown" ? p.current_occupation : "",
  );
  const [field, setField] = useState(p?.specialization && p.specialization !== "Unknown" ? p.specialization : "");
  const [age, setAge] = useState(p?.age_bracket && p.age_bracket !== "Unknown" ? p.age_bracket : "");
  const [city, setCity] = useState(p?.city && p.city !== "Unknown" ? p.city : "");
  const [phone, setPhone] = useState(p?.phone ?? "");
  const [heard, setHeard] = useState(p?.how_did_you_hear && p.how_did_you_hear !== "Unknown" ? p.how_did_you_hear : "");
  const [tried, setTried] = useState(false);
  const save = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>("/profile/complete", {
        current_occupation: occupation,
        specialization: field,
        age_bracket: age || null,
        city: city.trim() || "Unknown",
        phone: phone.trim() || null,
        how_did_you_hear: heard || "Unknown",
      }),
    onSuccess: async (r) => {
      toast({ tone: "good", text: r.message });
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate(from ?? "/my-learning", { replace: true });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (occupation && field) save.mutate();
  };
  const o = options.data;
  return (
    <AuthFrame
      title={`Welcome, ${me.user.name.split(" ")[0]}`}
      description="Two questions and your suggestions fit you better. The rest is optional."
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {save.isError && <Notice tone="bad">{errorText(save.error)}</Notice>}
        <Field label="What do you do now?" error={tried && !occupation ? "Choose one." : null}>
          <Select
            value={occupation}
            onChange={(e) => setOccupation(e.target.value)}
            options={[
              { value: "", label: "Choose one" },
              ...(o?.occupations ?? []).map((v) => ({ value: v, label: OCCUPATION_LABEL[v] ?? v })),
            ]}
          />
        </Field>
        <Field label="Which field are you in, or want to be in?" error={tried && !field ? "Choose one." : null}>
          <Select
            value={field}
            onChange={(e) => setField(e.target.value)}
            options={[
              { value: "", label: "Choose one" },
              ...(o?.specializations ?? []).map((v) => ({ value: v, label: v })),
            ]}
          />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Age" optional>
            <Select
              value={age}
              onChange={(e) => setAge(e.target.value)}
              options={[
                { value: "", label: "Rather not say" },
                ...(o?.age_brackets ?? []).map((v) => ({ value: v, label: v })),
              ]}
            />
          </Field>
          <Field label="City" optional>
            <Input
              autoComplete="address-level2"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              maxLength={60}
            />
          </Field>
        </div>
        <Field label="Phone" optional hint="Only if you want a counsellor to be able to call you.">
          <Input
            type="tel"
            autoComplete="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+91 98765 43210"
            maxLength={20}
          />
        </Field>
        <Field label="How did you hear about us?" optional>
          <Select
            value={heard}
            onChange={(e) => setHeard(e.target.value)}
            options={[
              { value: "", label: "Rather not say" },
              ...(o?.how_heard ?? []).map((v) => ({ value: v, label: v })),
            ]}
          />
        </Field>
        <Button type="submit" variant="primary" size="lg" loading={save.isPending}>
          Save and see my suggestions
        </Button>
        <button
          type="button"
          className="text-[14px] text-muted hover:text-ink"
          onClick={() => navigate(from ?? "/courses", { replace: true })}
        >
          Skip for now
        </button>
      </form>
    </AuthFrame>
  );
}
