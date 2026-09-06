import { useState } from "react";
import { NavLink, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Toaster } from "sonner";
import {
  LayoutDashboard, FileStack, GitCompareArrows, ClipboardCheck,
  Building2, MessagesSquare, Settings as SettingsIcon, Menu, X, History,
} from "lucide-react";

import Dashboard    from "./pages/Dashboard.jsx";
import Documents    from "./pages/Documents.jsx";
import Matches      from "./pages/Matches.jsx";
import Approvals    from "./pages/Approvals.jsx";
import Vendors      from "./pages/Vendors.jsx";
import Chat         from "./pages/Chat.jsx";
import SettingsPage      from "./pages/Settings.jsx";
import DocumentHistory   from "./pages/DocumentHistory.jsx";
import Login        from "./pages/Login.jsx";
import Signup       from "./pages/Signup.jsx";
import Landing      from "./pages/Landing.jsx";
import Product      from "./pages/Product.jsx";
import Pricing      from "./pages/Pricing.jsx";
import Docs         from "./pages/Docs.jsx";
import Privacy      from "./pages/Privacy.jsx";
import Terms        from "./pages/Terms.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import { useAuth }  from "./context/AuthContext.jsx";

const NAV = [
  { to: "/",          label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/documents",         label: "Documents", icon: FileStack        },
  { to: "/documents/history", label: "History",   icon: History          },
  { to: "/matches",   label: "Matches",   icon: GitCompareArrows },
  { to: "/approvals", label: "Approvals", icon: ClipboardCheck   },
  { to: "/vendors",   label: "Vendors",   icon: Building2        },
  { to: "/chat",      label: "Chat",      icon: MessagesSquare   },
  { to: "/settings",  label: "Settings",  icon: SettingsIcon     },
];

const pageVariants = {
  initial: { opacity: 0, y: 8  },
  enter:   { opacity: 1, y: 0,  transition: { duration: 0.18, ease: "easeOut" } },
  exit:    { opacity: 0, y: -4, transition: { duration: 0.12, ease: "easeIn"  } },
};

function AnimatedPage({ children }) {
  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="enter"
      exit="exit"
      className="min-h-full"
    >
      {children}
    </motion.div>
  );
}

/* ── App shell with sidebar (authenticated app) ──────────────────────────── */
function AppShell() {
  const { workspaceName, logout } = useAuth();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <>
      <Toaster position="top-right" richColors closeButton />

      <div className="min-h-screen flex bg-paper text-ink font-body">
        {/* Mobile overlay */}
        <AnimatePresence>
          {sidebarOpen && (
            <motion.div
              className="fixed inset-0 bg-ink/40 z-30 md:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSidebarOpen(false)}
            />
          )}
        </AnimatePresence>

        {/* Sidebar */}
        <aside
          className={[
            "fixed inset-y-0 left-0 z-40 w-60 shrink-0 border-r border-line bg-ledger text-paper flex flex-col",
            "transform transition-transform duration-200 ease-in-out",
            "md:static md:translate-x-0",
            sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          ].join(" ")}
        >
          <div className="px-5 py-6 border-b border-white/10 flex items-start justify-between">
            <div>
              <div className="font-display text-xl leading-none">SupplyChainIQ</div>
              <div className="text-xs text-wheat/80 mt-1 tracking-wide">Procurement intelligence</div>
            </div>
            <button
              className="md:hidden text-paper/60 hover:text-paper hover:bg-white/10 rounded p-0.5 transition-colors duration-150 mt-0.5"
              onClick={() => setSidebarOpen(false)}
              aria-label="Close navigation"
            >
              <X size={18} />
            </button>
          </div>

          <nav className="flex-1 py-4" aria-label="Main navigation">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 mx-3 mb-1 px-3 py-2 rounded-md text-sm transition-colors duration-150 focus-visible:outline-white ${
                    isActive
                      ? "bg-ledgerLight text-paper"
                      : "text-paper/70 hover:bg-white/10 hover:text-paper"
                  }`
                }
              >
                <Icon size={17} strokeWidth={1.75} aria-hidden="true" />
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="px-5 py-4 border-t border-white/10 text-xs text-paper/50">
            <div>Workspace: <span className="text-wheat">{workspaceName}</span></div>
            <button
              onClick={logout}
              className="mt-3 text-paper/60 hover:text-paper hover:bg-white/10 rounded px-1.5 py-0.5 -ml-1.5 transition-colors duration-150 focus-visible:outline-white"
            >
              Log out
            </button>
          </div>
        </aside>

        {/* Main content */}
        <div className="flex-1 min-w-0 flex flex-col">
          <div className="md:hidden flex items-center gap-3 px-4 py-3 border-b border-line bg-ledger text-paper">
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation"
              className="text-paper/70 hover:text-paper hover:bg-white/10 rounded p-1 transition-colors duration-150"
            >
              <Menu size={20} />
            </button>
            <span className="font-display text-lg leading-none">SupplyChainIQ</span>
          </div>

          <main className="flex-1">
            <AnimatePresence mode="wait" initial={false}>
              <Routes location={location} key={location.pathname}>
                <Route path="/"          element={<ProtectedRoute><AnimatedPage><Dashboard    /></AnimatedPage></ProtectedRoute>} />
                <Route path="/documents"         element={<ProtectedRoute><AnimatedPage><Documents      /></AnimatedPage></ProtectedRoute>} />
                <Route path="/documents/history" element={<ProtectedRoute><AnimatedPage><DocumentHistory /></AnimatedPage></ProtectedRoute>} />
                <Route path="/matches"   element={<ProtectedRoute><AnimatedPage><Matches      /></AnimatedPage></ProtectedRoute>} />
                <Route path="/approvals" element={<ProtectedRoute><AnimatedPage><Approvals    /></AnimatedPage></ProtectedRoute>} />
                <Route path="/vendors"   element={<ProtectedRoute><AnimatedPage><Vendors      /></AnimatedPage></ProtectedRoute>} />
                <Route path="/chat"      element={<ProtectedRoute><AnimatedPage><Chat         /></AnimatedPage></ProtectedRoute>} />
                <Route path="/settings"  element={<ProtectedRoute><AnimatedPage><SettingsPage /></AnimatedPage></ProtectedRoute>} />
                <Route path="*"          element={<Navigate to="/" replace />} />
              </Routes>
            </AnimatePresence>
          </main>
        </div>
      </div>
    </>
  );
}

/* ── Top-level router ────────────────────────────────────────────────────── */
export default function App() {
  const { status } = useAuth();
  const location   = useLocation();
  const path       = location.pathname;

  // Auth pages — full-screen, no sidebar, no auth check
  if (path === "/login")   return <><Toaster position="top-right" richColors closeButton /><Login   /></>;
  if (path === "/signup")  return <><Toaster position="top-right" richColors closeButton /><Signup  /></>;

  // Public marketing pages — no sidebar, no auth check
  if (path === "/product") return <><Toaster position="top-right" richColors closeButton /><Product /></>;
  if (path === "/pricing") return <><Toaster position="top-right" richColors closeButton /><Pricing /></>;
  if (path === "/docs")    return <><Toaster position="top-right" richColors closeButton /><Docs    /></>;
  if (path === "/privacy") return <><Toaster position="top-right" richColors closeButton /><Privacy /></>;
  if (path === "/terms")   return <><Toaster position="top-right" richColors closeButton /><Terms   /></>;

  // Root "/" — show Landing to anonymous visitors, Dashboard (inside AppShell) to authenticated ones
  // While auth is still resolving, show nothing to avoid a flash of Landing then Dashboard.
  if (path === "/") {
    if (status === "loading")       return null;
    if (status === "anonymous")     return <><Toaster position="top-right" richColors closeButton /><Landing /></>;
    // authenticated → fall through to AppShell below which has the sidebar + ProtectedRoute
  }

  // All other paths (and "/" when authenticated) — render inside the app shell with sidebar
  return <AppShell />;
}
