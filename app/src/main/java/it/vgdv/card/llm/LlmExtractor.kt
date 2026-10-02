package it.vgdv.card.llm

import it.vgdv.card.data.AppSettings
import it.vgdv.card.data.CardData
import it.vgdv.card.data.PhoneEntry
import it.vgdv.card.data.PhoneType
import it.vgdv.card.data.Provider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

data class ExtractResult(val card: CardData, val warning: String? = null)

/**
 * Struttura il testo OCR in un contatto. Invia SOLO testo (mai l'immagine) al provider scelto.
 */
class LlmExtractor {
    private val http = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    suspend fun extract(ocrText: String, groups: List<String>, s: AppSettings): ExtractResult =
        withContext(Dispatchers.IO) {
            if (s.provider == Provider.OFFLINE) return@withContext ExtractResult(OfflineParser.parse(ocrText))
            try {
                val prompt = buildPrompt(ocrText, groups)
                val raw = when (s.provider) {
                    Provider.GEMINI -> callGemini(prompt, s)
                    else -> callOpenAiCompatible(prompt, s)
                }
                ExtractResult(parseJson(raw, groups))
            } catch (e: Exception) {
                ExtractResult(
                    OfflineParser.parse(ocrText),
                    "LLM non disponibile (${e.message?.take(120)}). Usato il parser offline: verifica i campi.",
                )
            }
        }

    /** Verifica rapida di chiave/modello dalle impostazioni. */
    suspend fun testConnection(s: AppSettings): String = withContext(Dispatchers.IO) {
        if (s.provider == Provider.OFFLINE) return@withContext "Modalità offline: nessuna connessione necessaria."
        try {
            val sample = "Mario Rossi\nResponsabile Commerciale\nACME S.r.l.\nCell. 333 1234567\nmario.rossi@acme.it"
            val raw = if (s.provider == Provider.GEMINI) callGemini(buildPrompt(sample, listOf("Clienti")), s)
            else callOpenAiCompatible(buildPrompt(sample, listOf("Clienti")), s)
            val c = parseJson(raw, listOf("Clienti"))
            "OK ✓ — letto: ${c.firstName} ${c.lastName}, ${c.company}"
        } catch (e: Exception) {
            "Errore: ${e.message}"
        }
    }

    private fun buildPrompt(ocrText: String, groups: List<String>): String = """
Sei un assistente che estrae dati da biglietti da visita (spesso italiani).
Ricevi il testo OCR (può contenere errori) e restituisci SOLO un oggetto JSON valido, senza markdown, con questo schema:
{
  "firstName": string, "lastName": string, "company": string, "jobTitle": string,
  "phones": [{"number": string, "type": "MOBILE"|"WORK"|"MAIN"|"FAX"|"HOME"|"OTHER"}],
  "emails": [string], "website": string, "address": string,
  "suggestedGroups": [string],
  "summary": string
}
Regole:
- Correggi errori OCR evidenti (es. 0/O, 1/l) in email, siti e numeri.
- Numeri in formato internazionale (+39 per l'Italia se manca il prefisso). In Italia i numeri che iniziano con 3 sono cellulari.
- Titoli come Dott., Avv., Ing. NON fanno parte del nome; mettili in jobTitle se utili.
- "suggestedGroups": scegli 0-2 gruppi SOLO tra questi esistenti, scritti identici: ${JSONArray(groups)}
- "summary": max 200 caratteri in italiano, chi è e di cosa si occupa (settore/ruolo), dedotto dal biglietto. Non inventare.
- Campi assenti: stringa vuota o lista vuota.

Testo OCR (tra le righe ---):
---
$ocrText
---
""".trimIndent()

    private fun callGemini(prompt: String, s: AppSettings): String {
        require(s.geminiKey.isNotBlank()) { "chiave API Gemini mancante" }
        val body = JSONObject()
            .put("contents", JSONArray().put(JSONObject().put("parts", JSONArray().put(JSONObject().put("text", prompt)))))
            .put("generationConfig", JSONObject().put("temperature", 0).put("responseMimeType", "application/json"))
        val req = Request.Builder()
            .url("https://generativelanguage.googleapis.com/v1beta/models/${s.geminiModel}:generateContent")
            .header("x-goog-api-key", s.geminiKey)
            .post(body.toString().toRequestBody(jsonType))
            .build()
        val resp = execute(req)
        return JSONObject(resp).getJSONArray("candidates").getJSONObject(0)
            .getJSONObject("content").getJSONArray("parts").getJSONObject(0).getString("text")
    }

    private fun callOpenAiCompatible(prompt: String, s: AppSettings): String {
        require(s.nvidiaKey.isNotBlank()) { "chiave API NVIDIA mancante" }
        val body = JSONObject()
            .put("model", s.nvidiaModel)
            .put("temperature", 0)
            .put("max_tokens", 1024)
            .put(
                "messages", JSONArray()
                    .put(JSONObject().put("role", "system").put("content", "Rispondi solo con JSON valido."))
                    .put(JSONObject().put("role", "user").put("content", prompt))
            )
        val req = Request.Builder()
            .url("${s.nvidiaBaseUrl.trimEnd('/')}/chat/completions")
            .header("Authorization", "Bearer ${s.nvidiaKey}")
            .post(body.toString().toRequestBody(jsonType))
            .build()
        val resp = execute(req)
        return JSONObject(resp).getJSONArray("choices").getJSONObject(0)
            .getJSONObject("message").getString("content")
    }

    private fun execute(req: Request): String = http.newCall(req).execute().use { r ->
        val text = r.body?.string().orEmpty()
        if (!r.isSuccessful) error("HTTP ${r.code}: ${text.take(200)}")
        text
    }

    private fun parseJson(raw: String, groups: List<String>): CardData {
        val start = raw.indexOf('{')
        val end = raw.lastIndexOf('}')
        require(start >= 0 && end > start) { "risposta non JSON" }
        val o = JSONObject(raw.substring(start, end + 1))
        fun str(k: String) = o.optString(k, "").let { if (it == "null") "" else it.trim() }
        fun list(k: String): List<String> = o.optJSONArray(k)?.let { a ->
            (0 until a.length()).map { a.optString(it).trim() }.filter { it.isNotEmpty() }
        } ?: emptyList()

        val phones = o.optJSONArray("phones")?.let { a ->
            (0 until a.length()).mapNotNull { i ->
                val p = a.optJSONObject(i) ?: return@mapNotNull null
                val n = p.optString("number").trim()
                if (n.isEmpty()) null else PhoneEntry(OfflineParser.normalizePhone(n), PhoneType.parse(p.optString("type")))
            }
        }.orEmpty().distinctBy { it.number }

        return CardData(
            firstName = str("firstName"),
            lastName = str("lastName"),
            company = str("company"),
            jobTitle = str("jobTitle"),
            phones = phones,
            emails = list("emails").distinct(),
            website = str("website"),
            address = str("address"),
            suggestedGroups = list("suggestedGroups").filter { g -> groups.any { it.equals(g, ignoreCase = true) } },
            summary = str("summary"),
        )
    }
}
