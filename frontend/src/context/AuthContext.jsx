import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, clearTokens, login as apiLogin } from "../lib/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const [status, setStatus]     = useState("loading");
  const [workspace, setWorkspace] = useState(null);

  async function loadWorkspace() {
    const { data } = await api.get("/core/workspaces/");
    const workspaces = data.results ?? data;
    const firstWorkspace = workspaces[0];
    if (!firstWorkspace) throw new Error("No workspace available");
    setWorkspace(firstWorkspace);
    return firstWorkspace;
  }

  const resolveAuth = useCallback(async () => {
    /**
     * Re-run the token→workspace resolution on demand.
     * Called by Signup after storing tokens so the auth state updates
     * without a full page reload.
     */
    if (!localStorage.getItem("sciq_access")) {
      setStatus("anonymous");
      return;
    }
    try {
      await loadWorkspace();
      setStatus("authenticated");
    } catch {
      clearTokens();
      queryClient.clear();
      setWorkspace(null);
      setStatus("anonymous");
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    resolveAuth();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function login(username, password) {
    await apiLogin(username, password);
    try {
      await loadWorkspace();
      setStatus("authenticated");
    } catch (error) {
      clearTokens();
      queryClient.clear();
      setWorkspace(null);
      setStatus("anonymous");
      throw error;
    }
  }

  function logout() {
    clearTokens();
    queryClient.clear();
    setWorkspace(null);
    setStatus("anonymous");
  }

  return (
    <AuthContext.Provider
      value={{
        status,
        workspaceId:   workspace?.id   ?? null,
        workspaceName: workspace?.name ?? "—",
        login,
        logout,
        resolveAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
