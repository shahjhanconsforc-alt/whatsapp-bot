-- PostgreSQL schema for WhatsApp automation logging
-- Based on project architecture (sms_sent, sms_not_sent)

BEGIN;

DROP TABLE IF EXISTS sent_sms CASCADE;

CREATE TABLE IF NOT EXISTS sms_sent (
    id BIGSERIAL PRIMARY KEY,
    campaign_id VARCHAR(6) NOT NULL,
    campaign_name TEXT,
    phone VARCHAR(20),
    message TEXT,
    status VARCHAR(20),
    sent_at TIMESTAMP,
    content_kind VARCHAR(50),
    attachment_names TEXT,
    attachment_count INTEGER DEFAULT 0,
    payload_signature TEXT,
    content_summary TEXT,
    attachments_payload JSONB,
    dedupe_signature TEXT
);

DROP INDEX IF EXISTS ux_sms_sent_phone_message;
DROP INDEX IF EXISTS ux_sms_sent_phone_payload;

CREATE UNIQUE INDEX IF NOT EXISTS ux_sms_sent_phone_payload
    ON sms_sent (phone, payload_signature, campaign_id)
    WHERE payload_signature IS NOT NULL
      AND campaign_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_sms_sent_phone
    ON sms_sent (phone);

CREATE INDEX IF NOT EXISTS ix_sms_sent_sent_at
    ON sms_sent (sent_at DESC);

CREATE INDEX IF NOT EXISTS ix_sms_sent_campaign_id
    ON sms_sent (campaign_id);
CREATE INDEX IF NOT EXISTS ix_sms_sent_campaign_name
    ON sms_sent (campaign_name);


CREATE TABLE IF NOT EXISTS sms_not_sent (
    id BIGSERIAL PRIMARY KEY,
    campaign_id VARCHAR(6) NOT NULL,
    campaign_name TEXT,
    phone VARCHAR(20),
    reason TEXT,
    failed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_sms_not_sent_phone
    ON sms_not_sent (phone);

CREATE INDEX IF NOT EXISTS ix_sms_not_sent_failed_at
    ON sms_not_sent (failed_at DESC);

CREATE INDEX IF NOT EXISTS ix_sms_not_sent_campaign_id
    ON sms_not_sent (campaign_id);
CREATE INDEX IF NOT EXISTS ix_sms_not_sent_campaign_name
    ON sms_not_sent (campaign_name);

COMMIT;
