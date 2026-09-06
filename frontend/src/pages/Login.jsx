import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Loader2, AlertCircle } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";

import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout from "../components/AuthLayout.jsx";

const INPUT_BASE =
  "w-full border border-line rounded-md px-3 py-2 text-sm bg-white outline-none " +
  "transition-colors duration-150 focus:border-ledgerLight focus:ring-1 focus:ring-ledgerLight/30 " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

export default function Login() {
  const { login }  = useAuth();
  const navigate   = useNavigate();
  const location   = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username, password);
      navigate(location.state?.from?.pathname || "/", { replace: true });
    } catch {
      setError("Invalid username or password. Check your credentials and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Sign in" subtitle="Sign in to your procurement workspace">
      <form onSubmit={submit} noValidate className="space-y-5">

        {/* Inline error banner */}
        <AnimatePresence>
          {error && (
            <motion.p
              key="err"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.15 }}
              className="flex items-start gap-2 text-sm text-critical bg-critical/5 border border-critical/20 rounded-md px-3 py-2"
              role="alert"
            >
              <AlertCircle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
              {error}
            </motion.p>
          )}
        </AnimatePresence>

        <div className="space-y-1">
          <label className="block text-sm font-medium text-ink/80">
            Username or email
          </label>
          <input
            type="text"
            value={username}
            onChange={(e) => { setUsername(e.target.value); setError(""); }}
            autoComplete="username"
            required
            disabled={submitting}
            aria-invalid={!!error}
            className={clsx(INPUT_BASE, error && "border-critical")}
          />
        </div>

        <div className="space-y-1">
          <label className="block text-sm font-medium text-ink/80">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => { setPassword(e.target.value); setError(""); }}
            autoComplete="current-password"
            required
            disabled={submitting}
            aria-invalid={!!error}
            className={clsx(INPUT_BASE, error && "border-critical")}
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full flex items-center justify-center gap-2 rounded-md bg-ledger px-4 py-2.5 text-sm font-medium text-paper hover:bg-ledgerLight transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-ledgerLight"
        >
          {submitting && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}
          {submitting ? "Signing in…" : "Sign in"}
        </button>

        <p className="text-center text-sm text-ink/50">
          Don&apos;t have an account?{" "}
          <Link
            to="/signup"
            className="text-ledgerLight font-medium hover:underline focus-visible:outline-ledgerLight"
          >
            Sign up free
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
