"use client";

import { useState } from "react";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LensMark } from "./LensMark";

export function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading, login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="gate">
        <span className="spinner" />
      </div>
    );
  }

  if (user) return <>{children}</>;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="gate">
      <form className="card gate-card" onSubmit={submit}>
        <div className="brand">
          <LensMark size={28} />
          <span className="brand-name">
            Now<b>Lens</b>
          </span>
        </div>
        <h1>{mode === "login" ? "Sign in" : "Create your account"}</h1>
        <p className="sub">
          {mode === "login"
            ? "Access the ServiceNow expertise console."
            : "The first account becomes the administrator."}
        </p>

        <div className="stack">
          <div>
            <label className="lbl" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              className="field"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="lbl" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="field"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && <div className="alert">{error}</div>}

          <button className="btn" type="submit" disabled={busy}>
            {busy ? <span className="spinner" /> : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </div>

        <div className="toggle">
          {mode === "login" ? "No account yet? " : "Already have an account? "}
          <button
            type="button"
            onClick={() => {
              setError(null);
              setMode(mode === "login" ? "register" : "login");
            }}
          >
            {mode === "login" ? "Register" : "Sign in"}
          </button>
        </div>
      </form>
    </div>
  );
}
