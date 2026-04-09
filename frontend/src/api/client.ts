import ky from 'ky'

const api = ky.create({
  prefix: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 60_000,
  headers: {
    Accept: 'application/json',
  },
})

export default api
