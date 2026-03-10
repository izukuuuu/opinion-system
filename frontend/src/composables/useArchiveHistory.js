/**
 * useArchiveHistory — shared history normalisation and loading
 *
 * Replaces the duplicated normaliser / loadHistory implementations
 * across  useBasicAnalysis, useTopicBertopicView, and useReportGeneration.
 */

import { useApiBase } from './useApiBase'

const MAX_HISTORY = 12

/* ── Folder-name helpers ───────────────────────────────────────── */

/**
 * Parse a `"start_end"` style folder name into `{ start, end }`.
 */
export const splitFolderRange = (folder) => {
  const raw = String(folder || '').trim()
  if (!raw) return { start: '', end: '' }
  if (!raw.includes('_')) return { start: raw, end: raw }
  const [first, second] = raw.split('_', 2)
  const startText = String(first || '').trim()
  const endText = String(second || '').trim() || startText
  return { start: startText, end: endText }
}

/* ── Single-record normaliser ──────────────────────────────────── */

/**
 * Normalise one history record into a consistent shape.
 *
 * Works for all three response formats (analyze, bertopic, report).
 *
 * @param {Object}  record    - Raw record from API response
 * @param {Object}  defaults  - Fallback `{ topic, topic_identifier }`
 * @param {Object}  options   - `{ folderKey }` for archives fallback
 * @returns {Object|null}     - Normalised record or null
 */
export const normaliseRecord = (record, defaults = {}, options = {}) => {
  if (!record) return null

  const folderKey = options.folderKey || 'folder'
  const topic = String(record.topic || defaults.topic || '').trim()
  const topicIdentifier = String(
    record.topic_identifier || defaults.topic_identifier || topic
  ).trim()

  const folderRaw = String(
    record[folderKey] || record.folder || record.date || ''
  ).trim()
  const startRaw = String(record.start || '').trim()
  const endRaw = String(record.end || '').trim()

  // Derive start/end from folder if not explicitly set
  const range = startRaw
    ? { start: startRaw, end: endRaw || startRaw }
    : splitFolderRange(folderRaw)

  if (!topic || !range.start) return null

  const folder =
    folderRaw ||
    (range.start === range.end ? range.start : `${range.start}_${range.end}`)
  const id = String(record.id || `${topicIdentifier || topic}:${folder}`)

  const normalized = {
    id,
    topic,
    topic_identifier: topicIdentifier || topic,
    start: range.start,
    end: range.end,
    folder,
    updated_at: record.updated_at || record.lastRun || record.last_run || ''
  }

  // Preserve bertopic-specific fields when present
  if (record.display_topic || record.displayTopic) {
    normalized.display_topic = String(
      record.display_topic || record.displayTopic || topic
    ).trim()
  }
  if (Array.isArray(record.available_files)) {
    normalized.available_files = record.available_files
  }

  return normalized
}

/* ── Batch normaliser ──────────────────────────────────────────── */

/**
 * Normalise an array of history records and return up to MAX_HISTORY items.
 *
 * @param {Array}  records   - Raw array from API
 * @param {Object} defaults  - Fallback `{ topic, topic_identifier }`
 * @param {Object} options   - `{ folderKey }` override
 * @returns {Array}          - Normalised records array
 */
export const normaliseArchiveRecords = (
  records,
  defaults = {},
  options = {}
) => {
  if (!Array.isArray(records) || !records.length) return []
  return records
    .map((record) => normaliseRecord(record, defaults, options))
    .filter((entry) => entry && entry.start)
    .slice(0, MAX_HISTORY)
}

/* ── Response envelope normaliser ──────────────────────────────── */

/**
 * Extract records + defaults from varying response shapes.
 *
 * Handles:
 *   - `{ records, topic, topic_identifier }` (analyze, report)
 *   - `{ data: { records, topic, topic_identifier } }` (bertopic)
 *   - `{ archives: { <layer>: [...] } }` (archives fallback)
 *
 * @param {Object} response   - API response object
 * @param {string} layer      - "analyze" | "topic" | "reports"
 * @param {string} topicHint  - Fallback topic name
 */
export const normalizeArchiveResponse = (response, layer = '', topicHint = '') => {
  if (!response) return { records: [], defaults: {} }

  // Archives-style response
  if (response.archives && response.archives[layer]) {
    const entries = response.archives[layer] || []
    const defaults = {
      topic: response.display_name || response.project || topicHint,
      topic_identifier: response.topic || topicHint
    }
    return { records: entries, defaults, folderKey: 'date' }
  }

  // data-wrapped response (bertopic)
  const payload = response.data || response
  const records = payload.records || payload.data?.records || []
  const defaults = {
    topic: String(payload.topic || response.topic || topicHint).trim(),
    topic_identifier: String(
      payload.topic_identifier || response.topic_identifier || topicHint
    ).trim()
  }
  return { records, defaults }
}

/* ── Convenience: fetch + normalise ────────────────────────────── */

/**
 * Load history from an API endpoint and return normalised records.
 *
 * @param {string} apiPath   - Full API path with query string
 * @param {string} layer     - "analyze" | "topic" | "reports"
 * @param {string} topicHint - Fallback topic name
 * @returns {Promise<Array>} - Normalised records
 */
export const fetchAndNormaliseHistory = async (
  apiPath,
  layer = '',
  topicHint = ''
) => {
  const { callApi } = useApiBase()
  const response = await callApi(apiPath, { method: 'GET' })
  const { records, defaults, folderKey } = normalizeArchiveResponse(
    response,
    layer,
    topicHint
  )
  return normaliseArchiveRecords(records, defaults, folderKey ? { folderKey } : {})
}
