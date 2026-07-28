import { apiRequest } from './http'
import type { Project } from './types'

export function getProjects(): Promise<Project[]> {
  return apiRequest<Project[]>('/projects/')
}
