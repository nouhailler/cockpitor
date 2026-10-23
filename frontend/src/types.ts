export type Metrics = {
  collected_at: string;
  hostname: string;
  os: string;
  uptime_seconds: number;
  cpu_percent: number | null;
  cpu_cores: number[];
  load: number[];
  memory: { total: number; used: number; available: number; percent: number };
  swap: { total: number; used: number; percent: number };
  network: { received_bps: number | null; sent_bps: number | null };
  disks: {
    mount: string;
    device?: string;
    total?: number;
    used?: number;
    percent?: number;
    error: string | null;
  }[];
  temperatures: { name: string; celsius: number }[];
};
export type Process = {
  pid: number;
  name: string;
  user: string;
  cpu_percent: number | null;
  memory_percent: number;
  status: string;
};
export type History = {
  cpu_percent: number | null;
  memory_percent: number;
  collected_at: string;
}[];
export type Module = {
  status: string;
  message?: string;
  collected_at: string;
  latency_ms?: number;
  url?: string;
  models?: {
    name: string;
    size?: number;
    family?: string;
    quantization?: string;
  }[];
  loaded?: { name: string; size_vram?: number }[];
  engines?: {
    name: string;
    status: string;
    message?: string;
    version?: string;
    containers: {
      id: string;
      name: string;
      image: string;
      state: string;
      status: string;
      ports: string[];
    }[];
  }[];
};
