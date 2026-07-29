export type ReadinessStatus = 'PENDING' | 'SUCCESS' | 'PARTIAL_RESULT' | 'BLOCKED'

export interface HealthResponse {
  status: 'ok'
  service: string
}

export interface Project {
  project_id: string
  name: string
  code: string
  description: string
  timezone: string
  status: 'DRAFT' | 'ACTIVE' | 'ARCHIVED'
  owner: number | null
  owner_name: string
  created_at: string
  updated_at: string
}

export interface Person {
  person_id: string
  employee_id: string
  name: string
  email: string
  organization: string | null
  organization_name: string | null
  job_role: string
  employment_status: string
  timezone: string
  fte: string
}

export interface AnalysisRun {
  run_id: string
  project_id: string
  status: string
  readiness_status: ReadinessStatus
  missing_data: string[]
  limitations: string[]
  assumptions: string[]
  created_at: string
  updated_at: string
}
