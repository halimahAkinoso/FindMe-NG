
const API_BASE_URL = (
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : "Request failed. Please try again."
    );
  }

  return data;
}

export function validatePostcode(postcode) {
  return request("/api/postcodes/validate", {
    method: "POST",
    body: JSON.stringify({ postcode }),
  });
}

export function createDelivery(delivery) {
  return request("/api/deliveries", {
    method: "POST",
    body: JSON.stringify(delivery),
  });
}

export function getDeliveries(search = "", status = "") {
  const params = new URLSearchParams();

  if (search.trim()) params.set("search", search.trim());
  if (status) params.set("status", status);

  const query = params.toString();
  return request(`/api/deliveries${query ? `?${query}` : ""}`);
}

export function updateDeliveryStatus(id, status) {
  return request(
    `/api/deliveries/${encodeURIComponent(id)}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }
  );
}
