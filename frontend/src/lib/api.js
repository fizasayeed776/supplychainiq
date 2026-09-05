import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

export const api = axios.create({ baseURL: BASE_URL });

function getTokens() {
  return {
    access: localStorage.getItem("sciq_access"),
    refresh: localStorage.getItem("sciq_refresh"),
  };
}

export function setTokens({ access, refresh }) {
  if (access) localStorage.setItem("sciq_access", access);
  if (refresh) localStorage.setItem("sciq_refresh", refresh);
}

export function clearTokens() {
  localStorage.removeItem("sciq_access");
  localStorage.removeItem("sciq_refresh");
}

api.interceptors.request.use((config) => {
  const { access } = getTokens();
  if (access) config.headers.Authorization = `Bearer ${access}`;
  return config;
});

let refreshing = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const { refresh } = getTokens();
      if (!refresh) {
        clearTokens();
        return Promise.reject(error);
      }
      refreshing =
        refreshing ||
        axios
          .post(`${BASE_URL}/auth/token/refresh/`, { refresh })
          .then((res) => {
            setTokens({ access: res.data.access });
            return res.data.access;
          })
          .finally(() => {
            refreshing = null;
          });

      const newAccess = await refreshing;
      original.headers.Authorization = `Bearer ${newAccess}`;
      return api(original);
    }
    return Promise.reject(error);
  }
);

export async function login(username, password) {
  const { data } = await axios.post(`${BASE_URL}/auth/token/`, { username, password });
  setTokens(data);
  return data;
}
