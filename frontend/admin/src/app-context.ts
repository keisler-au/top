import { ApiClient, apiBaseUrl } from "./api/client.js";
import { QueryStore } from "./state/query-store.js";

export const api = new ApiClient(apiBaseUrl());
export const queryStore = new QueryStore();
