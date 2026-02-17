import axios from "axios";

const api = axios.create({ baseURL: "/api" });

// Bust Safari's aggressive HTTP cache by making every GET URL unique
api.interceptors.request.use((config) => {
  if (config.method === "get") {
    config.params = { ...config.params, _t: Date.now() };
  }
  return config;
});

export interface Site {
  id: number;
  url: string;
  domain: string;
  title: string | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrawlJob {
  id: number;
  site_id: number;
  status: "pending" | "running" | "completed" | "failed";
  pages_found: number;
  pages_crawled: number;
  pages_changed: number;
  pages_skipped: number;
  max_pages: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Page {
  id: number;
  url: string;
  title: string | null;
  description: string | null;
  category: string;
  relevance_score: number;
  depth: number;
}

export interface GeneratedFile {
  id: number;
  site_id: number;
  crawl_job_id: number | null;
  content: string;
  content_hash: string;
  is_edited: boolean;
  created_at: string;
}

export interface Schedule {
  id: number;
  site_id: number;
  cron_expression: string;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
}

export interface CrawlConfig {
  max_depth?: number;
  max_pages?: number;
}

// Sites
export const createSite = (url: string, config?: CrawlConfig) =>
  api.post<Site>("/sites", { url, ...config }).then((r) => r.data);

export const listSites = () =>
  api.get<{ sites: Site[] }>("/sites").then((r) => r.data.sites);

export const getSite = (id: number) =>
  api.get<Site>(`/sites/${id}`).then((r) => r.data);

export const deleteSite = (id: number) => api.delete(`/sites/${id}`);

// Crawl
export const startCrawl = (siteId: number, config?: CrawlConfig) =>
  api.post<CrawlJob>(`/sites/${siteId}/crawl`, config || {}).then((r) => r.data);

export const getCrawlStatus = (siteId: number, jobId: number) =>
  api.get<CrawlJob>(`/sites/${siteId}/crawl/${jobId}`).then((r) => r.data);

export const listCrawlJobs = (siteId: number) =>
  api.get<CrawlJob[]>(`/sites/${siteId}/crawl`).then((r) => r.data);

// Pages
export const listPages = (siteId: number) =>
  api.get<Page[]>(`/sites/${siteId}/pages`).then((r) => r.data);

// Generated files
export const getLlmsTxt = (siteId: number) =>
  api.get<GeneratedFile>(`/sites/${siteId}/llms-txt`).then((r) => r.data);

export const updateLlmsTxt = (siteId: number, content: string) =>
  api
    .put<GeneratedFile>(`/sites/${siteId}/llms-txt`, { content })
    .then((r) => r.data);

export const getLlmsTxtHistory = (siteId: number) =>
  api
    .get<GeneratedFile[]>(`/sites/${siteId}/llms-txt/history`)
    .then((r) => r.data);

// Schedule
export const getSchedule = (siteId: number) =>
  api.get<Schedule>(`/sites/${siteId}/schedule`).then((r) => r.data);

export const upsertSchedule = (
  siteId: number,
  cron_expression: string,
  is_active: boolean
) =>
  api
    .put<Schedule>(`/sites/${siteId}/schedule`, { cron_expression, is_active })
    .then((r) => r.data);

export const deleteSchedule = (siteId: number) =>
  api.delete(`/sites/${siteId}/schedule`);
