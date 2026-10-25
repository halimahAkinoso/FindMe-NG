
import { useCallback, useEffect, useState } from "react";
import {
  validatePostcode,
  createDelivery,
  getDeliveries,
  updateDeliveryStatus,
} from "./api";
import {
  MapPin,
  Package,
  Search,
  ShieldCheck,
  Truck,
  RefreshCw,
} from "lucide-react";
import "../index.css";

const initialForm = {
  customer_name: "",
  phone: "",
  postcode: "",
  state: "",
  lga: "",
  town: "",
  street: "",
  building_number: "",
  landmark: "",
  instructions: "",
  order_reference: "",
  postcode_verified: false,
};

// The official display format groups the postcode with spaces.
// Spaces and hyphens are removed before checking its length.
function normalizePostcode(value) {
  return value.replace(/[\s-]/g, "").toUpperCase();
}

function isValidPostcodeFormat(value) {
  return /^[A-Z0-9]{11}$/.test(normalizePostcode(value));
}

const inputFields = [
  ["customer_name", "Customer name", "e.g. Amina Bello"],
  ["phone", "Delivery phone", "e.g. 08012345678"],
  ["postcode", "Digital postcode", "OG 10 A16 BN 15"],
  ["state", "State", "e.g. Ogun"],
  ["lga", "Local government area", "e.g. Ijebu North East"],
  ["town", "Town / area", "e.g. Ijebu Ode"],
  ["street", "Street name", "Street or road"],
  ["building_number", "Building number", "House / shop number"],
  ["landmark", "Nearby landmark", "Help the rider identify the place"],
  ["order_reference", "Order reference", "e.g. FM-1001"],
];

export default function App() {
  const [form, setForm] = useState(initialForm);
  const [postcodeResult, setPostcodeResult] = useState(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [records, setRecords] = useState([]);
  const [activeTab, setActiveTab] = useState("create");

  const loadRecords = useCallback(async () => {
    try {
      setRecords(await getDeliveries(search));
    } catch (err) {
      setError(err.message || "Could not load delivery records.");
    }
  }, [search]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  function changeField(event) {
    const { name, value } = event.target;

    setForm((current) => ({
      ...current,
      [name]: value,
      ...(name === "postcode" ? { postcode_verified: false } : {}),
    }));

    if (name === "postcode") {
      setPostcodeResult(null);
      setError("");
      setNotice("");
    }
  }

  async function checkPostcode() {
    setError("");
    setNotice("");
    setPostcodeResult(null);

    const normalized = normalizePostcode(form.postcode);

    if (!isValidPostcodeFormat(form.postcode)) {
      setError(
        "Enter an 11-character alphanumeric postcode, " +
        "for example: OG 10 A16 BN 15."
      );
      return;
    }

    setChecking(true);

    try {
      // Send the normalized postcode to FastAPI.
      const result = await validatePostcode(normalized);

      setPostcodeResult(result);

      setForm((current) => ({
        ...current,
        postcode_verified:
          result.verified === true && result.valid === true,
      }));

      if (result.mode === "mock") {
        setNotice(
          "Format accepted for testing only. " +
          "Official NIPOST verification has not occurred."
        );
      } else if (
        result.verified === true &&
        result.valid === false
      ) {
        setError(
          result.message ||
          "The official service did not find this postcode."
        );
      } else {
        setNotice(
          result.message || "Postcode response received."
        );
      }
    } catch (err) {
      setError(err.message || "Could not check the postcode.");
    } finally {
      setChecking(false);
    }
  }

  async function submitDelivery(event) {
    event.preventDefault();
    setError("");
    setNotice("");

    if (!isValidPostcodeFormat(form.postcode)) {
      setError(
        "Enter an 11-character alphanumeric postcode, " +
        "for example: OG 10 A16 BN 15."
      );
      return;
    }

    const normalized = normalizePostcode(form.postcode);

    setSaving(true);

    try {
      await createDelivery({
        ...form,
        postcode: normalized,
      });

      setForm(initialForm);
      setPostcodeResult(null);
      setNotice("Delivery record saved successfully.");
      setActiveTab("records");
      await loadRecords();
    } catch (err) {
      setError(err.message || "Could not save the delivery record.");
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(id, status) {
    setError("");

    try {
      await updateDeliveryStatus(id, status);
      await loadRecords();
    } catch (err) {
      setError(err.message || "Could not update delivery status.");
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#">
          <span className="brand-icon">
            <MapPin size={23} />
          </span>
          <span>
            FindMe <b>NG</b>
          </span>
        </a>

        <span className="topbar-note">
          Smarter Nigerian deliveries
        </span>
      </header>

      <section className="hero">
        <span className="eyebrow">SMART ADDRESS ASSISTANT</span>

        <h1>
          Every delivery starts
          <br />
          with the right address.
        </h1>

        <p>
          Capture clearer addresses, verify postcodes where supported,
          and help your delivery team find the right destination.
        </p>

        <div className="hero-points">
          <span><ShieldCheck size={17} /> Address checks</span>
          <span><Package size={17} /> Organized orders</span>
          <span><Truck size={17} /> Rider-ready details</span>
        </div>
      </section>

      <nav className="tabs">
        <button
          type="button"
          className={activeTab === "create" ? "tab active" : "tab"}
          onClick={() => setActiveTab("create")}
        >
          <MapPin size={17} /> New delivery
        </button>

        <button
          type="button"
          className={activeTab === "records" ? "tab active" : "tab"}
          onClick={() => setActiveTab("records")}
        >
          <Package size={17} /> Delivery records
        </button>
      </nav>

      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert info">{notice}</div>}

      {activeTab === "create" ? (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Delivery address</h2>
              <p>Enter the destination and contact details.</p>
            </div>
            <MapPin size={25} />
          </div>

          <form onSubmit={submitDelivery}>
            <div className="form-grid">
              {inputFields.map(([name, label, placeholder]) => (
                <label
                  key={name}
                  className={name === "landmark" ? "wide" : ""}
                >
                  {label}

                  <input
                    name={name}
                    value={form[name]}
                    onChange={changeField}
                    placeholder={placeholder}
                    required
                    maxLength={name === "postcode" ? 32 : 200}
                    autoComplete={name === "phone" ? "tel" : "off"}
                    aria-describedby={
                      name === "postcode" ? "postcode-help" : undefined
                    }
                  />

                  {name === "postcode" && (
                    <span
                      className="field-help"
                      id="postcode-help"
                    >
                      Enter the complete code, e.g. OG 10 A16 BN 15.
                      Spaces and hyphens are allowed. Format checking
                      does not confirm that a postcode exists.
                    </span>
                  )}
                </label>
              ))}

              <label className="wide">
                Delivery instructions (optional)

                <textarea
                  name="instructions"
                  value={form.instructions}
                  onChange={changeField}
                  placeholder="Gate colour, entrance details, or directions..."
                  maxLength={1000}
                  rows={3}
                />
              </label>
            </div>

            <button
              type="button"
              className="button secondary"
              disabled={checking || !form.postcode.trim()}
              onClick={checkPostcode}
            >
              <ShieldCheck size={18} />
              {checking ? "Checking..." : "Check postcode"}
            </button>

            {postcodeResult && (
              <div className="postcode-result">
                <strong>
                  {postcodeResult.mode === "mock"
                    ? "Local test result"
                    : postcodeResult.mode === "official"
                      ? "Official service result"
                      : "Verification status"}
                </strong>

                <p>{postcodeResult.message}</p>

                {postcodeResult.location && (
                  <pre>
                    {JSON.stringify(
                      postcodeResult.location,
                      null,
                      2
                    )}
                  </pre>
                )}
              </div>
            )}

            <button
              className="button primary submit-button"
              type="submit"
              disabled={saving}
            >
              {saving ? "Saving..." : "Save delivery record"}
            </button>
          </form>
        </section>
      ) : (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Delivery records</h2>
              <p>Search and update saved deliveries.</p>
            </div>

            <button
              type="button"
              className="icon-button"
              onClick={loadRecords}
              title="Refresh records"
            >
              <RefreshCw size={18} />
            </button>
          </div>

          <div className="search-box">
            <Search size={18} />

            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search customer, postcode, order or landmark"
              aria-label="Search delivery records"
            />
          </div>

          {records.length === 0 ? (
            <p className="empty-state">
              No delivery records found.
            </p>
          ) : (
            <div className="records-list">
              {records.map((record) => (
                <article className="record" key={record.id}>
                  <div className="record-top">
                    <div>
                      <h3>{record.customer_name}</h3>
                      <span className="record-ref">
                        {record.order_reference}
                      </span>
                    </div>

                    <span className={`status ${record.status}`}>
                      {record.status}
                    </span>
                  </div>

                  <p>
                    {record.building_number}, {record.street},{" "}
                    {record.town}
                  </p>

                  <p className="muted">
                    {record.lga}, {record.state} · {record.postcode}
                  </p>

                  <p><b>Landmark:</b> {record.landmark}</p>
                  <p><b>Contact:</b> {record.phone}</p>

                  {record.instructions && (
                    <p>
                      <b>Instructions:</b> {record.instructions}
                    </p>
                  )}

                  <label className="status-control">
                    Update status

                    <select
                      value={record.status}
                      onChange={(event) =>
                        changeStatus(record.id, event.target.value)
                      }
                    >
                      <option value="pending">Pending</option>
                      <option value="dispatched">Dispatched</option>
                      <option value="delivered">Delivered</option>
                      <option value="cancelled">Cancelled</option>
                    </select>
                  </label>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      <footer>
        FindMe NG · Better addresses, better deliveries.
      </footer>
    </main>
  );
}
