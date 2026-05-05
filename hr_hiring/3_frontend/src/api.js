import axios from "axios";

const routerApiPath = import.meta.env.VITE_API_ROUTER_PATH;
const directApiBase = import.meta.env.VITE_API_BASE_URL;

export const baseURL = routerApiPath || directApiBase || "/hr_hiring_api";

export const api = axios.create({
  baseURL,
  timeout: 30000,
  withCredentials: true,
});

export async function fetchMe() {
  const { data } = await api.get("/me");
  return data;
}

export async function listPositions(status = "active") {
  const { data } = await api.get("/positions", { params: { status } });
  return data;
}

export async function createPosition(payload) {
  const { data } = await api.post("/positions", payload);
  return data;
}

export async function archivePosition(positionId) {
  const { data } = await api.patch(`/positions/${positionId}/archive`);
  return data;
}

export async function listPositionCandidates(positionId) {
  const { data } = await api.get(`/positions/${positionId}/candidates`);
  return data;
}

export async function createCandidate(payload) {
  const { data } = await api.post("/candidates", payload);
  return data;
}

export async function uploadPositionDocument(positionId, payload) {
  const form = new FormData();
  form.append("document_type", payload.document_type);
  if (payload.file) form.append("file", payload.file);
  if (payload.text_content) form.append("text_content", payload.text_content);
  const { data } = await api.post(`/positions/${positionId}/documents`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getCandidate(candidateId) {
  const { data } = await api.get(`/candidates/${candidateId}`);
  return data;
}

export async function uploadCandidateDocument(candidateId, payload) {
  const form = new FormData();
  form.append("document_type", payload.document_type);
  if (payload.file) form.append("file", payload.file);
  if (payload.text_content) form.append("text_content", payload.text_content);
  const { data } = await api.post(`/candidates/${candidateId}/documents`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function startEvaluation(candidateId) {
  const { data } = await api.post(`/evaluations/${candidateId}`);
  return data;
}

export async function getEvaluation(candidateId) {
  const { data } = await api.get(`/evaluations/${candidateId}`);
  return data;
}

export async function getPositionDetail(positionId) {
  const { data } = await api.get(`/positions/${positionId}`);
  return data;
}

export async function deletePositionDocument(positionId, documentId) {
  const { data } = await api.delete(`/positions/${positionId}/documents/${documentId}`);
  return data;
}

export async function getPosition(positionId) {
  const { data } = await api.get(`/positions/${positionId}/dashboard`);
  return data;
}

export async function getPositionDashboard(positionId) {
  const { data } = await api.get(`/positions/${positionId}/dashboard`);
  return data;
}

export async function updateCandidate(candidateId, payload) {
  const { data } = await api.patch(`/candidates/${candidateId}`, payload);
  return data;
}

export async function listCandidateDocuments(candidateId) {
  const { data } = await api.get(`/candidates/${candidateId}/documents`);
  return data;
}

export async function deleteCandidateDocument(candidateId, documentId) {
  const { data } = await api.delete(`/candidates/${candidateId}/documents/${documentId}`);
  return data;
}

export async function deleteCandidate(candidateId) {
  const { data } = await api.delete(`/candidates/${candidateId}`);
  return data;
}

export async function batchUploadCandidates(positionId, files) {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  const { data } = await api.post(`/positions/${positionId}/upload`, form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
  return data;
}

export async function createCandidateWithCV(positionId, { fullName, email, externalRef, file, textContent }) {
  const candidate = await createCandidate({ position_id: positionId, full_name: fullName, email, external_ref: externalRef });
  if (file || textContent) {
    await uploadCandidateDocument(candidate.candidate_id, {
      document_type: "cv",
      file,
      text_content: textContent,
    });
  }
  return candidate;
}
