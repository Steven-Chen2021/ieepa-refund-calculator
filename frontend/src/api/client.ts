import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
})

// Attach access token from memory store if present
apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export default apiClient
