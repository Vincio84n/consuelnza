package it.vgdv.card.llm

import com.google.i18n.phonenumbers.PhoneNumberUtil
import it.vgdv.card.data.CardData
import it.vgdv.card.data.PhoneEntry
import it.vgdv.card.data.PhoneType

/** Estrazione a regole, usata in modalità offline e come fallback se l'LLM fallisce. */
object OfflineParser {
    private val emailRx = Regex("""[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}""")
    private val webRx = Regex("""(?i)\b((https?://)?(www\.)[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(/\S*)?)""")
    private val phoneRx = Regex("""\+?\(?\d[\d\s./()\-]{6,}\d""")
    private val companyRx = Regex(
        """(?i)\b(s\.?r\.?l\.?s?|s\.?p\.?a\.?|s\.?n\.?c\.?|s\.?a\.?s\.?|studio|group|gruppo|ltd|gmbh|inc|consulting|associati|srls)\b"""
    )
    private val titleRx = Regex(
        """(?i)\b(ceo|cto|cfo|manager|direttore|responsabile|titolare|socio|avvocato|avv\.|dott\.?|dr\.?|ing\.?|geom\.?|rag\.?|commercialista|consulente|sales|account|amministratore|presidente|founder|partner)\b"""
    )
    private val addressRx = Regex("""(?i)\b(via|viale|v\.le|piazza|p\.zza|corso|c\.so|largo|strada|vicolo)\b""")

    fun parse(text: String): CardData {
        val lines = text.lines().map { it.trim() }.filter { it.isNotEmpty() }
        val emails = emailRx.findAll(text).map { it.value }.distinct().toList()
        val website = webRx.find(text)?.value
            ?: emails.firstOrNull()?.substringAfter('@')
                ?.takeUnless { it.contains("gmail") || it.contains("libero") || it.contains("hotmail") || it.contains("yahoo") }
                ?.let { "www.$it" }
            ?: ""

        val phones = mutableListOf<PhoneEntry>()
        for (line in lines) {
            if (emailRx.containsMatchIn(line)) continue
            for (m in phoneRx.findAll(line)) {
                val digits = m.value.count { it.isDigit() }
                if (digits !in 8..15) continue
                val norm = normalizePhone(m.value)
                if (phones.any { it.number == norm }) continue
                phones += PhoneEntry(norm, guessType(line, norm))
            }
        }

        val company = lines.firstOrNull { companyRx.containsMatchIn(it) } ?: ""
        val jobTitle = lines.firstOrNull { titleRx.containsMatchIn(it) && it != company } ?: ""
        val address = lines.filter { addressRx.containsMatchIn(it) || Regex("""\b\d{5}\b""").containsMatchIn(it) && !phoneRx.containsMatchIn(it) }
            .joinToString(", ")

        val nameLine = lines.firstOrNull { l ->
            l != company && l != jobTitle && !l.any { it.isDigit() } && !l.contains('@') &&
                !l.contains("www", true) && l.split(Regex("\\s+")).size in 2..4 &&
                l.split(Regex("\\s+")).all { w -> w.firstOrNull()?.isUpperCase() == true }
        } ?: ""
        val cleaned = nameLine.replace(Regex("""(?i)^(dott\.?ssa|dott\.?|dr\.?|avv\.?|ing\.?|geom\.?|rag\.?|arch\.?)\s+"""), "")
        val parts = cleaned.split(Regex("\\s+")).filter { it.isNotBlank() }
        val first = parts.dropLast(1).joinToString(" ")
        val last = parts.lastOrNull() ?: ""

        return CardData(
            firstName = if (parts.size >= 2) first else cleaned,
            lastName = if (parts.size >= 2) last else "",
            company = company,
            jobTitle = jobTitle,
            phones = phones,
            emails = emails,
            website = website,
            address = address,
        )
    }

    private fun guessType(line: String, number: String): PhoneType {
        val l = line.lowercase()
        return when {
            l.contains("fax") || Regex("""^f[.:\s]""").containsMatchIn(l) -> PhoneType.FAX
            l.contains("cell") || l.contains("mob") || Regex("""^m[.:\s]""").containsMatchIn(l) -> PhoneType.MOBILE
            number.startsWith("+393") -> PhoneType.MOBILE
            l.contains("centralino") || l.contains("switchboard") -> PhoneType.MAIN
            else -> PhoneType.WORK
        }
    }

    /** Normalizza in formato internazionale (+39...) quando possibile. */
    fun normalizePhone(raw: String): String {
        val util = PhoneNumberUtil.getInstance()
        return try {
            val parsed = util.parse(raw, "IT")
            if (util.isPossibleNumber(parsed)) util.format(parsed, PhoneNumberUtil.PhoneNumberFormat.E164)
            else raw.trim()
        } catch (e: Exception) {
            raw.trim()
        }
    }
}
