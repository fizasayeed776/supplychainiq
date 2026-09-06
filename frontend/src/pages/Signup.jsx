import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2, Eye, EyeOff, CheckCircle2, AlertCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";

import { api, setTokens } from "../lib/api.js";
import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout from "../components/AuthLayout.jsx";

/* ── Password strength meter ─────────────────────────────────────────────── */
function strengthOf(pw) {
  if (!pw) return { score: 0, label: "", color: "" };
  let score = 0;
  if (pw.length >= 8)  score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (score <= 1) return { score, label: "Weak",   color: "bg-critical" };
  if (score <= 3) return { score, label: "Fair",   color: "bg-minor"    };
  return            { score, label: "Strong", color: "bg-matched"  };
}

function StrengthBar({ password }) {
  const { score, label, color } = strengthOf(password);
  if (!password) return null;
  return (
    <div className="mt-1.5">
      <div className="flex gap-0.5 mb-1">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className={clsx(
              "h-1 flex-1 rounded-full transition-colors duration-300",
              i <= score ? color : "bg-line"
            )}
          />
        ))}
      </div>
      <div className="text-[11px] text-ink/40">{label}</div>
    </div>
  );
}

/* ── Field wrapper with inline error ─────────────────────────────────────── */
function Field({ label, error, children }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-ink/80">{label}</label>
      {children}
      <AnimatePresence>
        {error && (
          <motion.p
            key="err"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.15 }}
            className="flex items-center gap-1 text-xs text-critical"
            role="alert"
          >
            <AlertCircle size={11} aria-hidden="true" />
            {error}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

const INPUT_BASE =
  "w-full border border-line rounded-md px-3 py-2 text-sm bg-white outline-none " +
  "transition-colors duration-150 focus:border-ledgerLight focus:ring-1 focus:ring-ledgerLight/30 " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

export default function Signup() {
  const navigate  = useNavigate();
  const { resolveAuth } = useAuth();

  const [form, setForm] = useState({
    full_name:      "",
    email:          "",
    password:       "",
    confirm:        "",
    workspace_name: "",
  });
  const [showPw,  setShowPw]  = useState(false);
  const [errors,  setErrors]  = useState({});
  const [submitting, setSubmitting] = useState(false);

  function set(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }));
  }

  /* ── Client-side pre-validation ─────────────────────────────────────────── */
  function validate() {
    const errs = {};
    if (!form.full_name.trim())  errs.full_name = "Full name is required.";
    if (!form.email.trim())      errs.email     = "Email is required.";
    else if (!/\S+@\S+\.\S+/.test(form.email)) errs.email = "Enter a valid email address.";
    if (!form.password)          errs.password  = "Password is required.";
    else if (form.password.length < 8) errs.password = "Password must be at least 8 characters.";
    if (form.password !== form.confirm) errs.confirm = "Passwords do not match.";
    return errs;
  }

  async function submit(e) {
    e.preventDefault();
    const clientErrors = validate();
    if (Object.keys(clientErrors).length) { setErrors(clientErrors); return; }

    setSubmitting(true);
    setErrors({});
    try {
      const { data } = await api.post("/auth/register/", {
        email:          form.email.trim().toLowerCase(),
        password:       form.password,
        full_name:      form.full_name.trim(),
        workspace_name: form.workspace_name.trim() || undefined,
      });

      // Store tokens — reuse the same helper the Login page uses
      setTokens({ access: data.access, refresh: data.refresh });

      // Resolve auth state from the new token, then navigate to Dashboard
      await resolveAuth();
      navigate("/", { replace: true });

    } catch (err) {
      const serverErrors = err?.response?.data ?? {};
      // Map server field errors into our local errors state
      const mapped = {};
      if (serverErrors.email)          mapped.email          = [].concat(serverErrors.email).join(" ");
      if (serverErrors.password)       mapped.password       = [].concat(serverErrors.password).join(" ");
      if (serverErrors.full_name)      mapped.full_name      = [].concat(serverErrors.full_name).join(" ");
      if (serverErrors.workspace_name) mapped.workspace_name = [].concat(serverErrors.workspace_name).join(" ");
      if (serverErrors.non_field_errors) mapped._form        = [].concat(serverErrors.non_field_errors).join(" ");
      if (serverErrors.detail)           mapped._form        = serverErrors.detail;
      if (!Object.keys(mapped).length) mapped._form = "Something went wrong — please try again.";
      setErrors(mapped);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Create your workspace"
      subtitle="Set up your procurement intelligence workspace in minutes"
    >
      <form onSubmit={submit} noValidate className="space-y-5">

            {/* Form-level error */}
            <AnimatePresence>
              {errors._form && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-start gap-2 text-sm text-critical bg-critical/5 border border-critical/20 rounded-md px-3 py-2"
                  role="alert"
                >
                  <AlertCircle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
                  {errors._form}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Full name */}
            <Field label="Full name" error={errors.full_name}>
              <input
                type="text"
                value={form.full_name}
                onChange={(e) => set("full_name", e.target.value)}
                autoComplete="name"
                placeholder="Alice Nguyen"
                disabled={submitting}
                aria-invalid={!!errors.full_name}
                className={clsx(INPUT_BASE, errors.full_name && "border-critical focus:border-critical focus:ring-critical/20")}
              />
            </Field>

            {/* Email */}
            <Field label="Work email" error={errors.email}>
              <input
                type="email"
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
                autoComplete="email"
                placeholder="alice@acme.com"
                disabled={submitting}
                aria-invalid={!!errors.email}
                className={clsx(INPUT_BASE, errors.email && "border-critical focus:border-critical focus:ring-critical/20")}
              />
            </Field>

            {/* Password */}
            <Field label="Password" error={errors.password}>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  value={form.password}
                  onChange={(e) => set("password", e.target.value)}
                  autoComplete="new-password"
                  placeholder="Min 8 characters"
                  disabled={submitting}
                  aria-invalid={!!errors.password}
                  className={clsx(INPUT_BASE, "pr-10", errors.password && "border-critical focus:border-critical focus:ring-critical/20")}
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  aria-label={showPw ? "Hide password" : "Show password"}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink/30 hover:text-ink/60 transition-colors"
                >
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
              <StrengthBar password={form.password} />
            </Field>

            {/* Confirm password */}
            <Field label="Confirm password" error={errors.confirm}>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  value={form.confirm}
                  onChange={(e) => set("confirm", e.target.value)}
                  autoComplete="new-password"
                  placeholder="Repeat your password"
                  disabled={submitting}
                  aria-invalid={!!errors.confirm}
                  className={clsx(INPUT_BASE, errors.confirm && "border-critical focus:border-critical focus:ring-critical/20")}
                />
                {form.confirm && form.confirm === form.password && (
                  <CheckCircle2
                    size={15}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-matched pointer-events-none"
                    aria-hidden="true"
                  />
                )}
              </div>
            </Field>

            {/* Workspace / company name */}
            <Field label="Company / workspace name" error={errors.workspace_name}>
              <input
                type="text"
                value={form.workspace_name}
                onChange={(e) => set("workspace_name", e.target.value)}
                autoComplete="organization"
                placeholder="Acme Procurement (optional)"
                disabled={submitting}
                aria-invalid={!!errors.workspace_name}
                className={clsx(INPUT_BASE, errors.workspace_name && "border-critical")}
              />
              <p className="text-[11px] text-ink/35 mt-1">
                Creates your own private workspace. Leave blank to use your first name.
              </p>
            </Field>

            {/* Submit */}
            <button
              type="submit"
              disabled={submitting}
              className="w-full flex items-center justify-center gap-2 rounded-md bg-ledger px-4 py-2.5 text-sm font-medium text-paper hover:bg-ledgerLight transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-ledgerLight"
            >
              {submitting && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}
              {submitting ? "Creating workspace…" : "Create account"}
            </button>

            <p className="text-center text-sm text-ink/50">
              Already have an account?{" "}
              <Link
                to="/login"
                className="text-ledgerLight font-medium hover:underline focus-visible:outline-ledgerLight"
              >
                Sign in
              </Link>
            </p>
      </form>
    </AuthLayout>
  );
}
