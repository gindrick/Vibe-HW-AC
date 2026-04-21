import axios from "axios";

const routerApiPath = import.meta.env.VITE_API_ROUTER_PATH;
export const baseURL = routerApiPath || "/production_cards_api";

export const api = axios.create({
  baseURL,
  timeout: 60000,
  withCredentials: true,
});

export async function uploadCard(file) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/cards/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getCard(cardId) {
  const { data } = await api.get(`/cards/${cardId}`);
  return data;
}

export async function getPdfPage(cardId, pageNumber) {
  const { data } = await api.get(`/cards/${cardId}/pdf-page/${pageNumber}`);
  return data;
}

export async function updateCard(cardId, payload) {
  const { data } = await api.put(`/cards/${cardId}`, payload);
  return data;
}

export async function listCards(params) {
  const { data } = await api.get("/cards", { params });
  return data;
}

export function exportCardUrl(cardId) {
  return `${baseURL}/cards/${cardId}/export`;
}
