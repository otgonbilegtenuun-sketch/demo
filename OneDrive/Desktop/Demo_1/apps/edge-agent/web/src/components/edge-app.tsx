"use client";

import {
  Activity,
  AlertTriangle,
  Bell,
  Camera,
  CheckCircle2,
  ClipboardList,
  Gauge,
  LayoutDashboard,
  LogOut,
  Play,
  RefreshCcw,
  Shield,
  Square,
  Users,
  Wifi,
  WifiOff
} from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  API_BASE,
  ApiError,
  api,
  formatTime,
  mediaUrl,
  roleHome,
  wsUrl
} from "@/lib/api";
import type {
  AlertEvent,
  AttendanceRow,
  AttendanceStats,
  CameraRegistry,
  CameraStatus,
  Health,
  Incident,
  IncidentStats,
  ParentStudent,
  Role,
  Seat,
  EvalClip,
  EvalRecordStatus,
  Student,
  User
} from "@/lib/types";

type Notice = { tone: "info" | "success" | "warning" | "danger"; text: string };

const navByRole: Record<Role, Array<{ href: string; label: string; icon: React.ElementType }>> = {
  admin: [
    { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
    { href: "/monitor", label: "Monitor", icon: Camera },
    { href: "/enroll", label: "Enroll", icon: ClipboardList },
    { href: "/students", label: "Students", icon: Users },
    { href: "/incidents", label: "Incidents", icon: AlertTriangle },
    { href: "/seats", label: "Seats", icon: LayoutDashboard },
    { href: "/eval", label: "Eval", icon: Activity },
    { href: "/admin", label: "Admin", icon: Shield }
  ],
  teacher: [
    { href: "/teacher", label: "Classroom", icon: LayoutDashboard },
    { href: "/enroll", label: "Enroll", icon: ClipboardList },
    { href: "/students", label: "Students", icon: Users },
    { href: "/incidents", label: "Incidents", icon: AlertTriangle },
    { href: "/seats", label: "Seats", icon: LayoutDashboard },
    { href: "/eval", label: "Eval", icon: Activity }
  ],
  parent: [{ href: "/parent", label: "Parent", icon: Users }]
};

function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Request failed";
}

function percent(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${Math.round(value)}%`;
}

function statusTone(value: boolean): "success" | "danger" {
  return value ? "success" : "danger";
}

export default function EdgeApp() {
  const router = useRouter();
  const pathname = usePathname();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [socketLive, setSocketLive] = useState(false);

  const flash = useCallback((text: string, tone: Notice["tone"] = "info") => {
    setNotice({ text, tone });
    window.setTimeout(() => setNotice(null), 3200);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("mergen_token");
    setToken(null);
    setUser(null);
    router.replace("/login");
  }, [router]);

  useEffect(() => {
    const stored = localStorage.getItem("mergen_token");
    if (!stored) {
      setBooting(false);
      return;
    }
    setToken(stored);
    api<User>("GET", "/api/auth/me", stored)
      .then(setUser)
      .catch(() => {
        localStorage.removeItem("mergen_token");
        setToken(null);
        setUser(null);
      })
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    if (booting) return;
    if (!user && pathname !== "/" && pathname !== "/login") router.replace("/login");
    if (user && (pathname === "/" || pathname === "/login")) router.replace(roleHome(user.role));
  }, [booting, pathname, router, user]);

  useEffect(() => {
    if (!token || !user || user.role === "parent") {
      setSocketLive(false);
      return;
    }
    let closed = false;
    let socket: WebSocket | null = null;
    let retry: number | null = null;

    const connect = () => {
      if (closed) return;
      socket = new WebSocket(wsUrl(token));
      socket.onopen = () => setSocketLive(true);
      socket.onclose = () => {
        setSocketLive(false);
        if (!closed) retry = window.setTimeout(connect, 3000);
      };
      socket.onerror = () => setSocketLive(false);
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as { type?: string; payload?: Record<string, unknown> };
          if (payload.type === "alert") flash("New classroom alert received", "warning");
          if (payload.type === "incident") flash("New incident candidate received", "danger");
        } catch {
          // Ignore malformed realtime messages.
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      socket?.close();
    };
  }, [flash, token, user]);

  if (booting) return <Splash />;
  if (!user) {
    return (
      <>
        <LoginView
          onLogin={(nextToken, nextUser) => {
            localStorage.setItem("mergen_token", nextToken);
            setToken(nextToken);
            setUser(nextUser);
            router.replace(roleHome(nextUser.role));
          }}
          flash={flash}
        />
        <Toast notice={notice} />
      </>
    );
  }

  return (
    <AppShell user={user} socketLive={socketLive} onLogout={logout}>
      <RouteView pathname={pathname} token={token} user={user} flash={flash} />
      <Toast notice={notice} />
    </AppShell>
  );
}

function Splash() {
  return (
    <main className="splash">
      <div className="mark">M</div>
      <div>
        <h1>Mergen AI Edge</h1>
        <p>Loading local classroom system</p>
      </div>
    </main>
  );
}

function Toast({ notice }: { notice: Notice | null }) {
  if (!notice) return null;
  return <div className={`toast ${notice.tone}`}>{notice.text}</div>;
}

function LoginView({
  onLogin,
  flash
}: {
  onLogin: (token: string, user: User) => void;
  flash: (text: string, tone?: Notice["tone"]) => void;
}) {
  const [role, setRole] = useState<Role>("admin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      const res = await api<{ token: string; user: User }>("POST", "/api/auth/login", null, {
        username,
        password
      });
      if (res.user.role !== role) {
        flash(`Logged in as ${res.user.role}; switching to that workspace`, "warning");
      }
      onLogin(res.token, res.user);
    } catch (error) {
      flash(messageOf(error), "danger");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-copy">
        <div className="brand-row">
          <div className="mark">M</div>
          <span>Mergen AI Edge</span>
        </div>
        <h1>Classroom camera intelligence, running on the local edge.</h1>
        <p>
          Next.js + TypeScript frontend for attendance, safety alerts, camera health, and
          incident review. The backend still stays close to the cameras for low-cost demos.
        </p>
        <div className="login-system-line">
          <span>API</span>
          <code>{API_BASE}</code>
        </div>
      </section>

      <form className="login-panel" onSubmit={submit}>
        <div>
          <p className="eyebrow">Sign in</p>
          <h2>Choose workspace</h2>
        </div>
        <div className="role-grid">
          {(["admin", "teacher", "parent"] as Role[]).map((r) => (
            <button
              className={role === r ? "role-option active" : "role-option"}
              key={r}
              onClick={() => setRole(r)}
              type="button"
            >
              {r}
            </button>
          ))}
        </div>
        <label>
          Username
          <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          Password
          <input
            autoComplete="current-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button className="primary-btn" disabled={loading || !username || !password} type="submit">
          <Shield size={18} />
          {loading ? "Signing in" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

function AppShell({
  user,
  socketLive,
  onLogout,
  children
}: {
  user: User;
  socketLive: boolean;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const nav = navByRole[user.role] ?? [];

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand-row">
          <div className="mark">M</div>
          <span>Mergen Edge</span>
        </div>
        <nav>
          {nav.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <button className={active ? "nav-item active" : "nav-item"} key={item.href} onClick={() => router.push(item.href)}>
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">{user.role} workspace</p>
            <h1>{titleForPath(pathname, user.role)}</h1>
          </div>
          <div className="topbar-actions">
            <span className={socketLive ? "connection online" : "connection offline"}>
              {socketLive ? <Wifi size={16} /> : <WifiOff size={16} />}
              {socketLive ? "Realtime" : "Polling"}
            </span>
            <div className="user-chip">
              <span>{(user.full_name || user.username).slice(0, 2).toUpperCase()}</span>
              <div>
                <strong>{user.full_name || user.username}</strong>
                <small>{user.role}</small>
              </div>
            </div>
            <button className="icon-btn" onClick={onLogout} title="Logout">
              <LogOut size={18} />
            </button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}

function titleForPath(pathname: string, role: Role): string {
  if (pathname === "/monitor") return "Live monitor";
  if (pathname === "/enroll") return "Enrollment";
  if (pathname === "/students") return "Students";
  if (pathname === "/incidents") return "Incidents";
  if (pathname === "/seats") return "Seat map";
  if (pathname === "/eval") return "Evaluation";
  if (pathname === "/admin") return "Admin settings";
  if (pathname === "/teacher") return "Classroom";
  if (pathname === "/parent") return "Parent summary";
  return role === "admin" ? "School overview" : role === "teacher" ? "Classroom" : "Parent summary";
}

function RouteView({
  pathname,
  token,
  user,
  flash
}: {
  pathname: string;
  token: string | null;
  user: User;
  flash: (text: string, tone?: Notice["tone"]) => void;
}) {
  if (pathname === "/monitor") return <MonitorView token={token} user={user} flash={flash} />;
  if (pathname === "/enroll") return <EnrollView token={token} flash={flash} />;
  if (pathname === "/students") return <StudentsView token={token} />;
  if (pathname === "/incidents") return <IncidentsView token={token} flash={flash} />;
  if (pathname === "/seats") return <SeatsView token={token} flash={flash} />;
  if (pathname === "/eval") return <EvalView token={token} flash={flash} />;
  if (pathname === "/admin") return <AdminView token={token} user={user} flash={flash} />;
  if (pathname === "/parent") return <ParentView token={token} />;
  if (pathname === "/teacher") return <TeacherView token={token} />;
  return <OverviewView token={token} user={user} />;
}

function StatCard({
  label,
  value,
  detail,
  icon: Icon,
  tone = "neutral"
}: {
  label: string;
  value: string | number;
  detail?: string;
  icon: React.ElementType;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  return (
    <section className={`stat-card ${tone}`}>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        {detail ? <small>{detail}</small> : null}
      </div>
      <Icon size={22} />
    </section>
  );
}

function StatusBadge({ active, on, off }: { active: boolean; on: string; off: string }) {
  return <span className={`status-badge ${statusTone(active)}`}>{active ? on : off}</span>;
}

function ErrorPanel({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-panel">
      <AlertTriangle size={18} />
      <span>{message}</span>
      {onRetry ? (
        <button className="small-btn" onClick={onRetry}>
          <RefreshCcw size={15} />
          Retry
        </button>
      ) : null}
    </div>
  );
}

function EmptyPanel({ text }: { text: string }) {
  return <div className="empty-panel">{text}</div>;
}

function OverviewView({ token, user }: { token: string | null; user: User }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<AttendanceStats | null>(null);
  const [incidents, setIncidents] = useState<IncidentStats | null>(null);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const healthPromise = fetch(`${API_BASE}/api/health`, { cache: "no-store" }).then((r) => r.json() as Promise<Health>);
      if (user.role === "parent") {
        const parent = await api<ParentStudent>("GET", "/api/parent/student", token);
        setHealth(await healthPromise);
        setStats({
          total: 1,
          present: parent.today?.present ? 1 : 0,
          attendance_rate: parent.today?.present ? 100 : 0,
          avg_attention: parent.today?.attention_score ?? 0
        });
        return;
      }
      const [h, s, i, a] = await Promise.all([
        healthPromise,
        api<AttendanceStats>("GET", "/api/attendance/stats", token),
        api<IncidentStats>("GET", "/api/bullying/stats", token),
        api<AlertEvent[]>("GET", "/api/alerts/recent?since_id=0", token)
      ]);
      setHealth(h);
      setStats(s);
      setIncidents(i);
      setAlerts(a.slice(0, 6));
    } catch (error) {
      setError(messageOf(error));
    }
  }, [token, user.role]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="stack">
      {error ? <ErrorPanel message={error} onRetry={load} /> : null}
      <div className="stat-grid">
        <StatCard label="Students" value={health?.n_students ?? "-"} detail="registered locally" icon={Users} />
        <StatCard label="Attendance" value={percent(stats?.attendance_rate)} detail={`${stats?.present ?? "-"} present`} icon={CheckCircle2} tone="success" />
        <StatCard label="Attention" value={percent(stats?.avg_attention)} detail="class average" icon={Gauge} />
        <StatCard label="Pending incidents" value={incidents?.pending ?? "-"} detail="needs review" icon={AlertTriangle} tone="warning" />
      </div>
      <div className="two-col">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">System</p>
              <h2>Edge health</h2>
            </div>
            <StatusBadge active={!!health?.camera_running} on="Camera online" off="Camera offline" />
          </div>
          <dl className="detail-list">
            <div><dt>API status</dt><dd>{health?.status ?? "-"}</dd></div>
            <div><dt>Uptime</dt><dd>{health ? `${Math.round(health.uptime_s / 60)} min` : "-"}</dd></div>
            <div><dt>Exam mode</dt><dd>{health?.exam_mode ? "Enabled" : "Disabled"}</dd></div>
            <div><dt>Recording</dt><dd>{health?.recording ? "Yes" : "No"}</dd></div>
          </dl>
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Realtime</p>
              <h2>Recent alerts</h2>
            </div>
            <Bell size={19} />
          </div>
          <AlertList alerts={alerts} />
        </section>
      </div>
    </div>
  );
}

function TeacherView({ token }: { token: string | null }) {
  const [rows, setRows] = useState<AttendanceRow[]>([]);
  const [stats, setStats] = useState<AttendanceStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [today, s] = await Promise.all([
        api<AttendanceRow[]>("GET", "/api/attendance/today", token),
        api<AttendanceStats>("GET", "/api/attendance/stats", token)
      ]);
      setRows(today);
      setStats(s);
    } catch (error) {
      setError(messageOf(error));
    }
  }, [token]);

  useEffect(() => {
    void load();
    const id = window.setInterval(load, 10000);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <div className="stack">
      {error ? <ErrorPanel message={error} onRetry={load} /> : null}
      <div className="stat-grid compact">
        <StatCard label="Present" value={stats?.present ?? "-"} icon={CheckCircle2} tone="success" />
        <StatCard label="Attendance" value={percent(stats?.attendance_rate)} icon={Users} />
        <StatCard label="Attention" value={percent(stats?.avg_attention)} icon={Activity} />
      </div>
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Today</p>
            <h2>Attendance table</h2>
          </div>
          <button className="small-btn" onClick={load}><RefreshCcw size={15} /> Refresh</button>
        </div>
        <AttendanceTable rows={rows} />
      </section>
    </div>
  );
}

function ParentView({ token }: { token: string | null }) {
  const [data, setData] = useState<ParentStudent | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setData(await api<ParentStudent>("GET", "/api/parent/student", token));
    } catch (error) {
      setError(messageOf(error));
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const student = data?.student;
  const today = data?.today;

  return (
    <div className="stack">
      {error ? <ErrorPanel message={error} onRetry={load} /> : null}
      <section className="panel parent-panel">
        <div className="avatar-large">{student?.name?.slice(0, 2).toUpperCase() ?? "ST"}</div>
        <div>
          <p className="eyebrow">Student</p>
          <h2>{student?.name ?? "No linked student"}</h2>
          <p>{student?.class_name ?? "Class not set"}</p>
        </div>
        <StatusBadge active={!!today?.present} on="Present today" off="Absent today" />
      </section>
      <div className="stat-grid compact">
        <StatCard label="Attention" value={percent(today?.attention_score)} icon={Gauge} />
        <StatCard label="Alerts" value={today?.alert_count ?? 0} icon={Bell} tone={today?.alert_count ? "warning" : "neutral"} />
        <StatCard label="Arrival" value={formatTime(today?.timestamp)} icon={CheckCircle2} />
      </div>
    </div>
  );
}

function MonitorView({
  token,
  user,
  flash
}: {
  token: string | null;
  user: User;
  flash: (text: string, tone?: Notice["tone"]) => void;
}) {
  const [status, setStatus] = useState<CameraStatus | null>(null);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [cameraStatus, recent] = await Promise.all([
        api<CameraStatus>("GET", "/api/camera/status", token),
        api<AlertEvent[]>("GET", "/api/alerts/recent?since_id=0", token)
      ]);
      setStatus(cameraStatus);
      setAlerts(recent.slice(0, 8));
    } catch (error) {
      setError(messageOf(error));
    }
  }, [token]);

  useEffect(() => {
    void load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, [load]);

  async function cameraCommand(action: "start" | "stop") {
    if (user.role !== "admin") {
      flash("Only admin can control the camera", "warning");
      return;
    }
    setBusy(true);
    try {
      await api("POST", `/api/camera/${action}`, token);
      flash(action === "start" ? "Camera started" : "Camera stopped", "success");
      await load();
    } catch (error) {
      flash(messageOf(error), "danger");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      {error ? <ErrorPanel message={error} onRetry={load} /> : null}
      <section className="monitor-grid">
        <div className="video-panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Camera 01</p>
              <h2>Live feed</h2>
            </div>
            <StatusBadge active={!!status?.running} on="Running" off="Stopped" />
          </div>
          {status?.running ? (
            <img className="video-feed" src={mediaUrl("/video_feed", token)} alt="Live classroom camera feed" />
          ) : (
            <div className="video-empty">Camera feed is stopped</div>
          )}
          <div className="button-row">
            <button className="primary-btn" disabled={busy || user.role !== "admin"} onClick={() => void cameraCommand("start")}>
              <Play size={17} /> Start
            </button>
            <button className="secondary-btn" disabled={busy || user.role !== "admin"} onClick={() => void cameraCommand("stop")}>
              <Square size={17} /> Stop
            </button>
          </div>
        </div>
        <aside className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Recognition</p>
              <h2>Faces</h2>
            </div>
            <span className="counter">{status?.face_count ?? 0}</span>
          </div>
          {status?.faces?.length ? (
            <div className="face-list">
              {status.faces.map((face, idx) => (
                <div className="face-row" key={`${face.name}-${idx}`}>
                  <span>{face.name}</span>
                  <small>{face.looking_down ? "Looking down" : face.attentive ? "Attentive" : "Neutral"}</small>
                </div>
              ))}
            </div>
          ) : (
            <EmptyPanel text="No faces detected yet" />
          )}
        </aside>
      </section>
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Alerts</p>
            <h2>Monitor log</h2>
          </div>
          <button className="small-btn" onClick={load}><RefreshCcw size={15} /> Refresh</button>
        </div>
        <AlertList alerts={alerts} />
      </section>
    </div>
  );
}

function EnrollView({
  token,
  flash
}: {
  token: string | null;
  flash: (text: string, tone?: Notice["tone"]) => void;
}) {
  const [name, setName] = useState("");
  const [className, setClassName] = useState("Class A");
  const [images, setImages] = useState<Array<string | null>>([null, null, null]);
  const [busy, setBusy] = useState(false);

  function setFile(slot: number, file?: File) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setImages((prev) => {
        const next = [...prev];
        next[slot] = String(reader.result ?? "");
        return next;
      });
    };
    reader.readAsDataURL(file);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payloadImages = images.filter(Boolean) as string[];
    if (!name.trim() || !className.trim() || !payloadImages.length) {
      flash("Name, class, and at least one image are required", "warning");
      return;
    }
    setBusy(true);
    try {
      await api("POST", "/api/enroll", token, {
        name: name.trim(),
        class_name: className.trim(),
        role: "student",
        images: payloadImages
      });
      setName("");
      setImages([null, null, null]);
      flash("Student enrolled", "success");
    } catch (error) {
      flash(messageOf(error), "danger");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Face enrollment</p>
            <h2>Register a student</h2>
          </div>
        </div>
        <form className="enroll-form" onSubmit={submit}>
          <label>
            Student name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Class
            <input value={className} onChange={(e) => setClassName(e.target.value)} />
          </label>
          <div className="upload-grid">
            {images.map((image, idx) => (
              <label className={image ? "upload-slot filled" : "upload-slot"} key={idx}>
                <input accept="image/*" type="file" onChange={(e) => setFile(idx, e.target.files?.[0])} />
                {image ? <img src={image} alt={`Enrollment preview ${idx + 1}`} /> : <span>Photo {idx + 1}</span>}
              </label>
            ))}
          </div>
          <button className="primary-btn" disabled={busy} type="submit">
            <ClipboardList size={17} />
            {busy ? "Saving" : "Enroll student"}
          </button>
        </form>
      </section>
    </div>
  );
}

function StudentsView({ token }: { token: string | null }) {
  const [rows, setRows] = useState<Student[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setRows(await api<Student[]>("GET", "/api/students", token));
    } catch (error) {
      setError(messageOf(error));
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => `${row.name} ${row.class_name ?? ""}`.toLowerCase().includes(q));
  }, [query, rows]);

  return (
    <div className="stack">
      {error ? <ErrorPanel message={error} onRetry={load} /> : null}
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Roster</p>
            <h2>Students</h2>
          </div>
          <div className="toolbar">
            <input placeholder="Search students" value={query} onChange={(e) => setQuery(e.target.value)} />
            <button className="small-btn" onClick={load}><RefreshCcw size={15} /> Refresh</button>
          </div>
        </div>
        <StudentTable rows={filtered} />
      </section>
    </div>
  );
}

function IncidentsView({
  token,
  flash
}: {
  token: string | null;
  flash: (text: string, tone?: Notice["tone"]) => void;
}) {
  const [rows, setRows] = useState<Incident[]>([]);
  const [stats, setStats] = useState<IncidentStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [recent, s] = await Promise.all([
        api<Incident[]>("GET", "/api/bullying/recent?limit=80", token),
        api<IncidentStats>("GET", "/api/bullying/stats", token)
      ]);
      setRows(recent);
      setStats(s);
    } catch (error) {
      setError(messageOf(error));
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function review(id: number, outcome: string) {
    try {
      await api("POST", `/api/bullying/${id}/review`, token, { outcome });
      flash("Incident review saved", "success");
      await load();
    } catch (error) {
      flash(messageOf(error), "danger");
    }
  }

  return (
    <div className="stack">
      {error ? <ErrorPanel message={error} onRetry={load} /> : null}
      <div className="stat-grid compact">
        <StatCard label="Pending" value={stats?.pending ?? "-"} icon={AlertTriangle} tone="warning" />
        <StatCard label="This week" value={stats?.week_total ?? "-"} icon={Activity} />
        <StatCard label="Reviewed" value={stats?.reviewed_week ?? "-"} icon={CheckCircle2} tone="success" />
      </div>
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Review queue</p>
            <h2>Incident candidates</h2>
          </div>
          <button className="small-btn" onClick={load}><RefreshCcw size={15} /> Refresh</button>
        </div>
        {rows.length ? (
          <div className="incident-list">
            {rows.map((incident) => (
              <article className="incident-card" key={incident.id}>
                <div>
                  <div className="incident-title">
                    <strong>{incident.primary_signal ?? "incident"}</strong>
                    <span>{Math.round((incident.score ?? 0) * 100)}%</span>
                  </div>
                  <p>{(incident.involved_names ?? []).join(", ") || "No identified student"}</p>
                  <small>{formatTime(incident.timestamp)}</small>
                </div>
                <div className="button-row">
                  <button className="small-btn" onClick={() => void review(incident.id, "confirmed")}>Confirm</button>
                  <button className="small-btn" onClick={() => void review(incident.id, "false_positive")}>False</button>
                  <button className="small-btn" onClick={() => void review(incident.id, "inconclusive")}>Unsure</button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyPanel text="No incident candidates" />
        )}
      </section>
    </div>
  );
}

function AdminView({
  token,
  user,
  flash
}: {
  token: string | null;
  user: User;
  flash: (text: string, tone?: Notice["tone"]) => void;
}) {
  const [health, setHealth] = useState<Health | null>(null);
  const [cameras, setCameras] = useState<CameraRegistry | null>(null);
  const [flags, setFlags] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (user.role !== "admin") {
      setError("Admin role required");
      return;
    }
    try {
      setError(null);
      const [h, c, f] = await Promise.all([
        fetch(`${API_BASE}/api/health`, { cache: "no-store" }).then((r) => r.json() as Promise<Health>),
        api<CameraRegistry>("GET", "/api/cameras", token),
        api<Record<string, boolean>>("GET", "/api/admin/flags", token)
      ]);
      setHealth(h);
      setCameras(c);
      setFlags(f);
    } catch (error) {
      setError(messageOf(error));
    }
  }, [token, user.role]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveFlags() {
    try {
      await api("POST", "/api/admin/flags", token, flags);
      flash("Feature flags saved", "success");
    } catch (error) {
      flash(messageOf(error), "danger");
    }
  }

  return (
    <div className="stack">
      {error ? <ErrorPanel message={error} onRetry={load} /> : null}
      <div className="two-col">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Operations</p>
              <h2>System health</h2>
            </div>
            <StatusBadge active={!!health?.camera_running} on="Camera online" off="Camera offline" />
          </div>
          <dl className="detail-list">
            <div><dt>Students</dt><dd>{health?.n_students ?? "-"}</dd></div>
            <div><dt>Uptime</dt><dd>{health ? `${Math.round(health.uptime_s / 60)} min` : "-"}</dd></div>
            <div><dt>Last incident</dt><dd>{health?.last_incident ?? "-"}</dd></div>
          </dl>
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">Camera registry</p>
              <h2>Configured cameras</h2>
            </div>
            <span className="counter">{cameras?.cameras?.length ?? 0}</span>
          </div>
          {cameras?.cameras?.length ? (
            <div className="camera-list">
              {cameras.cameras.map((camera, idx) => (
                <div className="face-row" key={idx}>
                  <span>{String(camera.id ?? `camera-${idx + 1}`)}</span>
                  <small>{String(camera.label ?? camera.source ?? "local source")}</small>
                </div>
              ))}
            </div>
          ) : (
            <EmptyPanel text="No camera registry entries returned" />
          )}
        </section>
      </div>
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Detection</p>
            <h2>Feature flags</h2>
          </div>
          <button className="small-btn" onClick={() => void saveFlags()}><Shield size={15} /> Save</button>
        </div>
        <div className="flag-grid">
          {Object.entries(flags).map(([key, value]) => (
            <label className="switch-row" key={key}>
              <span>{key.replaceAll("_", " ")}</span>
              <input
                checked={value}
                type="checkbox"
                onChange={(e) => setFlags((prev) => ({ ...prev, [key]: e.target.checked }))}
              />
            </label>
          ))}
        </div>
      </section>
    </div>
  );
}

function SeatsView({
  token,
  flash
}: {
  token: string | null;
  flash: (text: string, tone?: Notice["tone"]) => void;
}) {
  const [seats, setSeats] = useState<Seat[]>([]);
  const [occupancy, setOccupancy] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [seatRows, occ] = await Promise.all([
        api<Seat[]>("GET", "/api/seats?class_name=Class%20A", token),
        api<Record<string, unknown>>("GET", "/api/seats/occupancy", token).catch(() => null)
      ]);
      setSeats(seatRows);
      setOccupancy(occ);
    } catch (error) {
      setError(messageOf(error));
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function clearSeats() {
    try {
      await api("DELETE", "/api/seats?class_name=Class%20A", token);
      flash("Seat map cleared", "success");
      await load();
    } catch (error) {
      flash(messageOf(error), "danger");
    }
  }

  return (
    <div className="stack">
      {error ? <ErrorPanel message={error} onRetry={load} /> : null}
      <div className="stat-grid compact">
        <StatCard label="Seats" value={seats.length} icon={LayoutDashboard} />
        <StatCard label="Occupancy signal" value={occupancy ? "Live" : "Idle"} icon={Activity} tone={occupancy ? "success" : "neutral"} />
        <StatCard label="Class" value="Class A" icon={Users} />
      </div>
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Seat map</p>
            <h2>Assigned seats</h2>
          </div>
          <div className="button-row">
            <button className="small-btn" onClick={load}><RefreshCcw size={15} /> Refresh</button>
            <button className="small-btn danger" onClick={() => void clearSeats()}>Clear</button>
          </div>
        </div>
        {seats.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Rectangle</th>
                  <th>Student ID</th>
                </tr>
              </thead>
              <tbody>
                {seats.map((seat, idx) => (
                  <tr key={seat.id ?? idx}>
                    <td>{seat.student_name ?? "Unassigned"}</td>
                    <td>{seat.x1},{seat.y1} - {seat.x2},{seat.y2}</td>
                    <td>{seat.student_id ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyPanel text="No seats assigned yet. Use the legacy canvas editor if you need to draw rectangles today." />
        )}
      </section>
    </div>
  );
}

const evalLabels = ["fight", "crowd_bully", "normal", "crowd_normal", "note_passing"];

function EvalView({
  token,
  flash
}: {
  token: string | null;
  flash: (text: string, tone?: Notice["tone"]) => void;
}) {
  const [clips, setClips] = useState<EvalClip[]>([]);
  const [status, setStatus] = useState<EvalRecordStatus | null>(null);
  const [results, setResults] = useState<Record<string, unknown> | null>(null);
  const [duration, setDuration] = useState(30);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [clipRows, recStatus, evalResults] = await Promise.all([
        api<EvalClip[]>("GET", "/api/eval/clips", token),
        api<EvalRecordStatus>("GET", "/api/eval/record/status", token),
        api<Record<string, unknown>>("GET", "/api/eval/results", token).catch(() => null)
      ]);
      setClips(clipRows);
      setStatus(recStatus);
      setResults(evalResults);
    } catch (error) {
      setError(messageOf(error));
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function startRecording() {
    setBusy(true);
    try {
      await api("POST", "/api/eval/record/start", token, { duration_s: duration });
      flash("Eval recording started", "success");
      await load();
    } catch (error) {
      flash(messageOf(error), "danger");
    } finally {
      setBusy(false);
    }
  }

  async function stopRecording() {
    setBusy(true);
    try {
      await api("POST", "/api/eval/record/stop", token);
      flash("Eval recording stopped", "success");
      await load();
    } catch (error) {
      flash(messageOf(error), "danger");
    } finally {
      setBusy(false);
    }
  }

  async function labelClip(filename: string, truth_label: string) {
    try {
      await api("POST", `/api/eval/clips/${encodeURIComponent(filename)}/label`, token, { truth_label });
      await load();
    } catch (error) {
      flash(messageOf(error), "danger");
    }
  }

  async function runEval() {
    setBusy(true);
    try {
      setResults(await api<Record<string, unknown>>("POST", "/api/eval/run", token));
      flash("Evaluation completed", "success");
    } catch (error) {
      flash(messageOf(error), "danger");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      {error ? <ErrorPanel message={error} onRetry={load} /> : null}
      <div className="stat-grid compact">
        <StatCard label="Clips" value={clips.length} icon={Camera} />
        <StatCard label="Recorder" value={status?.recording ? "Recording" : "Idle"} icon={Activity} tone={status?.recording ? "warning" : "neutral"} />
        <StatCard label="Last result" value={results?.never_run ? "None" : "Ready"} icon={CheckCircle2} tone={results?.never_run ? "neutral" : "success"} />
      </div>
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="eyebrow">Ground truth</p>
            <h2>Record and label clips</h2>
          </div>
          <button className="small-btn" onClick={load}><RefreshCcw size={15} /> Refresh</button>
        </div>
        <div className="button-row eval-controls">
          <input min={5} max={600} type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
          <button className="primary-btn" disabled={busy || status?.recording} onClick={() => void startRecording()}>
            <Play size={17} /> Record
          </button>
          <button className="secondary-btn" disabled={busy || !status?.recording} onClick={() => void stopRecording()}>
            <Square size={17} /> Stop
          </button>
          <button className="secondary-btn" disabled={busy || !clips.length} onClick={() => void runEval()}>
            <Activity size={17} /> Run eval
          </button>
        </div>
        {clips.length ? (
          <div className="clip-list">
            {clips.map((clip) => (
              <div className="clip-row" key={clip.filename}>
                <div>
                  <strong>{clip.filename}</strong>
                  <small>{Math.round(clip.size_bytes / 1024)} KB</small>
                </div>
                <select value={clip.truth_label ?? ""} onChange={(e) => void labelClip(clip.filename, e.target.value)}>
                  <option value="">Unlabeled</option>
                  {evalLabels.map((label) => <option key={label} value={label}>{label}</option>)}
                </select>
              </div>
            ))}
          </div>
        ) : (
          <EmptyPanel text="No evaluation clips yet" />
        )}
      </section>
    </div>
  );
}

function AlertList({ alerts }: { alerts: AlertEvent[] }) {
  if (!alerts.length) return <EmptyPanel text="No alerts yet" />;
  return (
    <div className="alert-list">
      {alerts.map((alert) => (
        <div className="alert-row" key={alert.id}>
          <AlertTriangle size={17} />
          <div>
            <strong>{alert.student_name || "Unknown"}</strong>
            <span>{alert.alert_type.replaceAll("_", " ")}</span>
          </div>
          <time>{formatTime(alert.timestamp)}</time>
        </div>
      ))}
    </div>
  );
}

function AttendanceTable({ rows }: { rows: AttendanceRow[] }) {
  if (!rows.length) return <EmptyPanel text="No attendance rows" />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Class</th>
            <th>Status</th>
            <th>Attention</th>
            <th>Alerts</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.name}</td>
              <td>{row.class_name ?? "-"}</td>
              <td><StatusBadge active={row.present} on="Present" off="Absent" /></td>
              <td>{percent(row.attention_score)}</td>
              <td>{row.alert_count}</td>
              <td>{formatTime(row.timestamp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StudentTable({ rows }: { rows: Student[] }) {
  if (!rows.length) return <EmptyPanel text="No students found" />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Class</th>
            <th>Face</th>
            <th>Today</th>
            <th>Attention</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.name}</td>
              <td>{row.class_name ?? "-"}</td>
              <td>{row.has_face ? "Ready" : "Missing"}</td>
              <td>{row.present_today ? "Present" : "Absent"}</td>
              <td>{percent(row.attention_score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
