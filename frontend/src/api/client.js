import axios from 'axios';

const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.data?.detail) {
      return Promise.reject(new Error(error.response.data.detail));
    }
    return Promise.reject(new Error('网络请求失败，请稍后重试'));
  }
);

export const api = {
  login: (payload) => client.post('/auth/login', payload).then((res) => res.data),
  getSummary: () => client.get('/dashboard/summary').then((res) => res.data),
  listChannels: () => client.get('/channels').then((res) => res.data),
  getChannel: (id) => client.get(`/channels/${id}`).then((res) => res.data),
  createChannel: (payload) => client.post('/channels', payload).then((res) => res.data),
  updateChannel: (id, payload) => client.put(`/channels/${id}`, payload).then((res) => res.data),
  deleteChannel: (id) => client.delete(`/channels/${id}`),
  updateThreshold: (id, payload) => client.post(`/channels/thresholds/${id}`, payload).then((res) => res.data),
  syncSamples: (payload) => client.post('/samples/sync', payload).then((res) => res.data),
  listSamples: (params) => client.get('/samples', { params }).then((res) => res.data),
  exportSamples: (params) => client.get('/samples/export', { params, responseType: 'blob' }),
  listAlarms: (params) => client.get('/alarms', { params }).then((res) => res.data),
  resolveAlarm: (id, resolved = true) => client.post(`/alarms/${id}/resolve`, { resolved }).then((res) => res.data),
};
