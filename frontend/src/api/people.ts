import { apiRequest } from './http'
import type { Person } from './types'

export function getPeople(): Promise<Person[]> {
  return apiRequest<Person[]>('/people/')
}
