export type Role = "admin" | "teacher" | "parent";

export type User = {
  id: number;
  username: string;
  role: Role;
  full_name?: string | null;
  student_id?: number | null;
};

export type LoginResponse = {
  token: string;
  user: User;
};

export type Health = {
  status: string;
  uptime_s: number;
  camera_running: boolean;
  exam_mode: boolean;
  recording: boolean;
  n_students: number;
  last_incident?: string | null;
  feature_flags?: Record<string, boolean>;
};

export type CameraFace = {
  name: string;
  attentive?: boolean | null;
  looking_down?: boolean | null;
  uniform_on?: boolean | null;
};

export type CameraStatus = {
  running: boolean;
  exam_mode: boolean;
  face_count: number;
  faces: CameraFace[];
};

export type CameraRegistry = {
  default_id?: string;
  cameras: Array<Record<string, unknown>>;
};

export type AttendanceRow = {
  id: number;
  name: string;
  class_name?: string | null;
  present: boolean;
  timestamp?: string | null;
  attention_score: number;
  alert_count: number;
};

export type AttendanceStats = {
  total?: number;
  present?: number;
  attendance_rate?: number;
  avg_attention?: number;
};

export type AttentionPoint = {
  time_label: string;
  avg_attention: number;
};

export type Student = {
  id: number;
  name: string;
  class_name?: string | null;
  role?: string | null;
  has_face?: boolean;
  present_today?: boolean;
  attention_score?: number;
  created_at?: string | null;
};

export type AlertEvent = {
  id: number;
  student_name?: string | null;
  alert_type: string;
  timestamp?: string | null;
};

export type Incident = {
  id: number;
  timestamp?: string | null;
  score?: number;
  primary_signal?: string | null;
  involved_names?: string[];
  concurrent_signals?: string[];
  reviewed?: boolean | number;
  review_outcome?: string | null;
  video_clip_path?: string | null;
};

export type IncidentStats = {
  pending?: number;
  week_total?: number;
  reviewed_week?: number;
  by_signal_week?: Array<{ primary_signal: string; count: number }>;
};

export type ParentStudent = {
  student?: Student;
  today?: {
    present: boolean;
    timestamp?: string | null;
    attention_score?: number;
    alert_count?: number;
  };
};

export type Seat = {
  id?: number;
  student_id?: number | null;
  student_name?: string | null;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

export type EvalClip = {
  filename: string;
  size_bytes: number;
  modified: number;
  url: string;
  truth_label?: string | null;
};

export type EvalRecordStatus = {
  recording?: boolean;
  path?: string | null;
  elapsed_s?: number;
  max_seconds?: number;
};
