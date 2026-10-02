package it.vgdv.card.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

enum class Provider(val label: String) {
    OFFLINE("Offline (solo regole, nessun invio dati)"),
    GEMINI("Google Gemini"),
    NVIDIA("NVIDIA / OpenAI-compatibile"),
}

enum class NameFormat(val label: String) {
    FIRST_LAST("Nome Cognome"),
    LAST_FIRST("Cognome Nome"),
    FIRST_LAST_COMPANY("Nome Cognome (Azienda)"),
    COMPANY_FIRST_LAST("Azienda - Nome Cognome"),
}

data class AppSettings(
    val provider: Provider = Provider.GEMINI,
    val geminiKey: String = "",
    val geminiModel: String = "gemini-2.5-flash",
    val nvidiaKey: String = "",
    val nvidiaModel: String = "meta/llama-3.3-70b-instruct",
    val nvidiaBaseUrl: String = "https://integrate.api.nvidia.com/v1",
    val nameFormat: NameFormat = NameFormat.FIRST_LAST,
    val accountName: String = "",
    val accountType: String = "",
    val currentEvent: String = "",
)

class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    // Le chiavi API sono cifrate con Android Keystore; fallback su prefs normali
    // solo se il Keystore del dispositivo non è utilizzabile.
    private val secure: SharedPreferences = try {
        EncryptedSharedPreferences.create(
            context,
            "secure_settings",
            MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    } catch (e: Exception) {
        prefs
    }

    fun load(): AppSettings {
        val d = AppSettings()
        return AppSettings(
            provider = runCatching { Provider.valueOf(prefs.getString("provider", d.provider.name)!!) }
                .getOrDefault(d.provider),
            geminiKey = secure.getString("geminiKey", "") ?: "",
            geminiModel = prefs.getString("geminiModel", d.geminiModel) ?: d.geminiModel,
            nvidiaKey = secure.getString("nvidiaKey", "") ?: "",
            nvidiaModel = prefs.getString("nvidiaModel", d.nvidiaModel) ?: d.nvidiaModel,
            nvidiaBaseUrl = prefs.getString("nvidiaBaseUrl", d.nvidiaBaseUrl) ?: d.nvidiaBaseUrl,
            nameFormat = runCatching { NameFormat.valueOf(prefs.getString("nameFormat", d.nameFormat.name)!!) }
                .getOrDefault(d.nameFormat),
            accountName = prefs.getString("accountName", "") ?: "",
            accountType = prefs.getString("accountType", "") ?: "",
            currentEvent = prefs.getString("currentEvent", "") ?: "",
        )
    }

    fun save(s: AppSettings) {
        secure.edit()
            .putString("geminiKey", s.geminiKey.trim())
            .putString("nvidiaKey", s.nvidiaKey.trim())
            .apply()
        prefs.edit()
            .putString("provider", s.provider.name)
            .putString("geminiModel", s.geminiModel.trim())
            .putString("nvidiaModel", s.nvidiaModel.trim())
            .putString("nvidiaBaseUrl", s.nvidiaBaseUrl.trim().trimEnd('/'))
            .putString("nameFormat", s.nameFormat.name)
            .putString("accountName", s.accountName)
            .putString("accountType", s.accountType)
            .putString("currentEvent", s.currentEvent)
            .apply()
    }
}
