CREATE TABLE IF NOT EXISTS customers (
    location_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    data_residency TEXT,
    relationship_start DATE NOT NULL,
    account_status TEXT NOT NULL,
    account_closure_date DATE
);

CREATE TABLE IF NOT EXISTS transactions (
    location_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    txn_date DATE NOT NULL,
    amount NUMERIC NOT NULL,
    instrument_type TEXT NOT NULL,
    is_processor_held BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS marketing_consents (
    location_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    consent_status TEXT NOT NULL,
    consent_granted_date DATE NOT NULL,
    consent_withdrawn_date DATE,
    purpose TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kyc_documents (
    location_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    customer_location_id TEXT NOT NULL REFERENCES customers (location_id),
    doc_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    uploaded_date DATE NOT NULL
);
