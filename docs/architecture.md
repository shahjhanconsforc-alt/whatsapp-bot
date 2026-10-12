
# 📐 WhatsApp Automation Tool – Architecture

## **1. Overview**

This document describes the **architecture** of the WhatsApp automation tool built using **FastAPI**.
It defines **components, workflow, validation gates, and logging/tracking**.

---

## **2. High-Level Architecture**

```
        ┌───────────────┐
        │   User / UI   │
        └───────┬───────┘
                │ Upload File & Monitor Progress
                ▼
        ┌───────────────┐
        │   FastAPI App │
        └───────┬───────┘
                │
     ┌──────────┴──────────┐
     │ Sequential Processing│
     └──────────┬──────────┘
                │
        ┌───────┴────────┐
        │ Validation Gates│
        └───────┬────────┘
                │
 ┌──────────────┴──────────────┐
 │ Database / Logging (PostgreSQL)│
 └──────────────┬──────────────┘
                │
        ┌───────┴────────┐
        │ WhatsApp Web   │
        └────────────────┘
```

---

## **3. Components & Responsibilities**

| Component                              | Responsibility                                                   |
| -------------------------------------- | ---------------------------------------------------------------- |
| **FastAPI App**                        | Main server & API endpoints, manages UI interactions             |
| **UI**                                 | Upload file, show progress & gate status, display logs           |
| **Database (PostgreSQL)**              | Store `sent_sms` and `not_sent_sms` tables, track all steps      |
| **File Reader**                        | Read `.csv` / `.xlsx`, extract and normalize numbers             |
| **Validation (`validation_check.py`)** | Format, country code, space removal, retry logic                 |
| **WhatsApp Sender**                    | Open new chat, check number existence, send message sequentially |
| **Status Tracker**                     | Log each step and update live UI                                 |

---

## **4. Sequence of Operations**

1. **UI & App Initialization**

   * Show “App running” status
   * Initialize logging system

2. **Database Connection Gate**

   * Connect to PostgreSQL
   * Log success/failure
   * Stop if connection fails

3. **WhatsApp Web Login Gate**

   * Open session & verify login
   * Log success/failure
   * Stop if not logged in

4. **File Upload Gate**

   * Accept `.csv` / `.xlsx`
   * Extract phone numbers
   * Log success/failure
   * Stop if invalid

5. **Number Processing Loop**
   For each number:

   * Check if exists in `sent_sms` → skip if exists
   * Validate number (`validation_check.py`)
   * Open new WhatsApp chat
   * Check WhatsApp existence
   * If exists → send message & log in `sent_sms`
   * If not → log reason in `not_sent_sms`

6. **UI Updates**

   * Show live progress:

     * Total numbers
     * Sent
     * Failed
     * Current number
     * Not sent numbers

7. **Completion**

   * Display summary
   * Export logs if required

---

## **5. Database Schema**

### `sent_sms`

| Column    | Type      | Description                |
| --------- | --------- | -------------------------- |
| id        | Integer   | Auto-increment primary key |
| phone     | Text      | Recipient number           |
| message   | Text      | Sent message content       |
| status    | Text      | `sent`                     |
| timestamp | Timestamp | Time of send               |

### `not_sent_sms`

| Column    | Type      | Description                |
| --------- | --------- | -------------------------- |
| id        | Integer   | Auto-increment primary key |
| phone     | Text      | Recipient number           |
| reason    | Text      | Reason not sent            |
| timestamp | Timestamp | Time of attempt            |

---

## **6. Logging & Tracking**

* All operations logged with **timestamps**
* Logs include:

  * DB connection status
  * WhatsApp login status
  * File upload success/failure
  * Each number processing:

    * Validation result
    * WhatsApp check result
    * Send status
    * Reason for failure if any
* Live updates reflected in UI

---

## **7. Key Design Principles**

* Sequential processing (one number at a time)
* Step-by-step validation gates
* Pre-check database to avoid duplicate sends
* Centralized logging and progress tracking
* Modular structure for easier maintenance

---

## **8. Folder Structure**

```
project/
│── main.py
│── routes/
│── services/
│   ├── file_reader.py
│   ├── sender.py
│   ├── db.py
│   └── validation_check.py
│── models/
│── static/
│── templates/
│── logs/
```

---
