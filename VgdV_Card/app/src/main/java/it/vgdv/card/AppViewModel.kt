package it.vgdv.card

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import it.vgdv.card.contacts.AccountInfo
import it.vgdv.card.contacts.ContactsRepo
import it.vgdv.card.contacts.GroupInfo
import it.vgdv.card.data.AppSettings
import it.vgdv.card.data.CardData
import it.vgdv.card.data.SettingsStore
import it.vgdv.card.llm.LlmExtractor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

enum class Screen { HOME, PROCESSING, REVIEW, SETTINGS }

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val store = SettingsStore(app)
    private val contacts = ContactsRepo(app)
    private val extractor = LlmExtractor()

    var screen by mutableStateOf(Screen.HOME)
    var settings by mutableStateOf(store.load())
        private set
    var status by mutableStateOf("")

    // Stato della revisione
    var card by mutableStateOf(CardData())
    var ocrText by mutableStateOf("")
    var warning by mutableStateOf<String?>(null)
    var duplicates by mutableStateOf<List<String>>(emptyList())
    var event by mutableStateOf("")
    var freeNote by mutableStateOf("")
    var groups by mutableStateOf<List<GroupInfo>>(emptyList())
    val selectedGroups = mutableStateListOf<Long>()
    var lastSavedUri by mutableStateOf<Uri?>(null)

    var accounts by mutableStateOf<List<AccountInfo>>(emptyList())
    var testResult by mutableStateOf("")

    val currentAccount: AccountInfo?
        get() = settings.accountName.takeIf { it.isNotEmpty() }?.let { AccountInfo(it, settings.accountType) }

    fun updateSettings(s: AppSettings) {
        settings = s
        store.save(s)
    }

    fun refreshContactsMeta() {
        viewModelScope.launch {
            val (acc, grp) = withContext(Dispatchers.IO) {
                runCatching { contacts.accounts() }.getOrDefault(emptyList()) to
                    runCatching { contacts.groups(currentAccount) }.getOrDefault(emptyList())
            }
            accounts = acc
            groups = grp
            // Primo avvio: seleziona automaticamente il primo account Google.
            if (settings.accountName.isEmpty()) {
                acc.firstOrNull { it.type == "com.google" }?.let {
                    updateSettings(settings.copy(accountName = it.name, accountType = it.type))
                    groups = withContext(Dispatchers.IO) { runCatching { contacts.groups(it) }.getOrDefault(emptyList()) }
                }
            }
        }
    }

    fun onScanned(pages: List<Uri>) {
        if (pages.isEmpty()) return
        screen = Screen.PROCESSING
        status = "Lettura del biglietto (OCR)…"
        viewModelScope.launch {
            try {
                val text = Ocr.read(getApplication(), pages)
                ocrText = text
                groups = withContext(Dispatchers.IO) { runCatching { contacts.groups(currentAccount) }.getOrDefault(emptyList()) }
                status = "Analisi con ${settings.provider.label}…"
                val res = extractor.extract(text, groups.map { it.title }, settings)
                card = res.card
                warning = res.warning
                event = settings.currentEvent
                freeNote = ""
                lastSavedUri = null
                selectedGroups.clear()
                selectedGroups += groups.filter { g -> res.card.suggestedGroups.any { it.equals(g.title, true) } }.map { it.id }
                checkDuplicates()
                screen = Screen.REVIEW
            } catch (e: Exception) {
                status = "Errore: ${e.message}"
                screen = Screen.HOME
            }
        }
    }

    fun checkDuplicates() {
        viewModelScope.launch {
            duplicates = withContext(Dispatchers.IO) { runCatching { contacts.findDuplicates(card) }.getOrDefault(emptyList()) }
        }
    }

    fun toggleGroup(id: Long) {
        if (id in selectedGroups) selectedGroups.remove(id) else selectedGroups.add(id)
    }

    fun createGroup(title: String) {
        val acc = currentAccount ?: return
        if (title.isBlank()) return
        viewModelScope.launch {
            val g = withContext(Dispatchers.IO) { runCatching { contacts.createGroup(title.trim(), acc) }.getOrNull() }
            if (g != null) {
                groups = (groups + g).sortedBy { it.title.lowercase() }
                selectedGroups += g.id
            }
        }
    }

    fun previewName(): String = contacts.displayName(card, settings.nameFormat)

    fun buildNote(): String {
        val date = SimpleDateFormat("dd/MM/yyyy", Locale.ITALY).format(Date())
        return buildString {
            append("Conosciuto il $date")
            if (event.isNotBlank()) append(" — ${event.trim()}")
            append('\n')
            if (freeNote.isNotBlank()) append("Note: ${freeNote.trim()}\n")
            if (card.summary.isNotBlank()) append("Profilo: ${card.summary.trim()}\n")
            append("[Acquisito con VgdV Card]")
        }
    }

    fun save(onDone: (Boolean, String) -> Unit) {
        viewModelScope.launch {
            val result = withContext(Dispatchers.IO) {
                runCatching {
                    contacts.save(card, settings.nameFormat, currentAccount, selectedGroups.toList(), buildNote())
                }
            }
            result.onSuccess { uri ->
                lastSavedUri = uri
                if (event != settings.currentEvent) updateSettings(settings.copy(currentEvent = event))
                onDone(true, "Contatto \"${previewName()}\" salvato in rubrica")
            }.onFailure { onDone(false, "Errore salvataggio: ${it.message}") }
        }
    }

    fun testConnection() {
        testResult = "Verifica in corso…"
        viewModelScope.launch { testResult = extractor.testConnection(settings) }
    }
}
