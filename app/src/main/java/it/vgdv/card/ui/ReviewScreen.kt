package it.vgdv.card.ui

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.speech.RecognizerIntent
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import it.vgdv.card.AppViewModel
import it.vgdv.card.Screen
import it.vgdv.card.data.PhoneEntry
import it.vgdv.card.data.PhoneType

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ReviewScreen(vm: AppViewModel, openContact: (Uri) -> Unit) {
    val ctx = LocalContext.current
    val card = vm.card
    var saving by remember { mutableStateOf(false) }
    var showOcr by remember { mutableStateOf(false) }
    var newGroup by remember { mutableStateOf("") }

    val voice = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        if (r.resultCode == Activity.RESULT_OK) {
            val said = r.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
            if (said.isNotBlank()) vm.freeNote = listOf(vm.freeNote, said).filter { it.isNotBlank() }.joinToString(" ")
        }
    }

    Scaffold(topBar = {
        TopAppBar(
            title = { Text("Verifica contatto") },
            navigationIcon = { TextButton(onClick = { vm.screen = Screen.HOME }) { Text("✕") } },
        )
    }) { pad ->
        Column(
            Modifier.padding(pad).padding(horizontal = 16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            vm.warning?.let { Text("⚠ $it", color = MaterialTheme.colorScheme.error) }
            if (vm.duplicates.isNotEmpty()) {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Text(
                        "Possibile duplicato già in rubrica:\n" + vm.duplicates.joinToString("\n") { "• $it" },
                        Modifier.padding(12.dp),
                    )
                }
            }

            Text("Salvato come: ${vm.previewName()}", style = MaterialTheme.typography.titleMedium)

            Field("Nome", card.firstName) { vm.card = card.copy(firstName = it) }
            Field("Cognome", card.lastName) { vm.card = card.copy(lastName = it) }
            Field("Azienda", card.company) { vm.card = card.copy(company = it) }
            Field("Ruolo", card.jobTitle) { vm.card = card.copy(jobTitle = it) }

            Section("Telefoni")
            card.phones.forEachIndexed { i, p ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = p.number,
                        onValueChange = { v -> vm.card = card.copy(phones = card.phones.replace(i, p.copy(number = v))) },
                        singleLine = true,
                        modifier = Modifier.weight(1f),
                    )
                    Picker(p.type.label, PhoneType.entries, { it.label }, { t ->
                        vm.card = card.copy(phones = card.phones.replace(i, p.copy(type = t)))
                    }, Modifier.padding(start = 6.dp))
                    IconButton(onClick = { vm.card = card.copy(phones = card.phones.filterIndexed { j, _ -> j != i }) }) {
                        Icon(Icons.Default.Delete, contentDescription = "Rimuovi")
                    }
                }
            }
            TextButton(onClick = { vm.card = card.copy(phones = card.phones + PhoneEntry("", PhoneType.MOBILE)) }) {
                Text("+ Aggiungi telefono")
            }

            Field("Email (separate da virgola)", card.emails.joinToString(", ")) { v ->
                vm.card = card.copy(emails = v.split(',').map { it.trim() }.filter { it.isNotEmpty() })
            }
            Field("Sito web", card.website) { vm.card = card.copy(website = it) }
            Field("Indirizzo", card.address, singleLine = false) { vm.card = card.copy(address = it) }

            Section("Gruppi rubrica")
            if (vm.currentAccount == null) {
                Text("Nessun account Google selezionato: i gruppi non sono disponibili (impostazioni).",
                    style = MaterialTheme.typography.bodySmall)
            } else {
                if (vm.groups.isEmpty()) Text("Nessun gruppo esistente.", style = MaterialTheme.typography.bodySmall)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    vm.groups.forEach { g ->
                        FilterChip(
                            selected = g.id in vm.selectedGroups,
                            onClick = { vm.toggleGroup(g.id) },
                            label = { Text(g.title) },
                        )
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = newGroup, onValueChange = { newGroup = it }, singleLine = true,
                        label = { Text("Nuovo gruppo") }, modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = { vm.createGroup(newGroup); newGroup = "" }) { Text("Crea") }
                }
            }

            Section("Note")
            Field("Evento / luogo", vm.event) { vm.event = it }
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = vm.freeNote, onValueChange = { vm.freeNote = it },
                    label = { Text("Nota libera") }, modifier = Modifier.weight(1f),
                )
                TextButton(onClick = {
                    val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                        .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                        .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "it-IT")
                        .putExtra(RecognizerIntent.EXTRA_PROMPT, "Detta una nota sul contatto")
                    try {
                        voice.launch(intent)
                    } catch (e: ActivityNotFoundException) {
                        Toast.makeText(ctx, "Riconoscimento vocale non disponibile", Toast.LENGTH_SHORT).show()
                    }
                }) { Text("🎤 Detta") }
            }
            Field("Profilo (AI)", card.summary, singleLine = false) { vm.card = card.copy(summary = it) }

            Card {
                Text(vm.buildNote(), Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall)
            }

            TextButton(onClick = { showOcr = !showOcr }) { Text(if (showOcr) "Nascondi testo OCR" else "Mostra testo OCR") }
            if (showOcr) Text(vm.ocrText, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)

            HorizontalDivider()
            val saved = vm.lastSavedUri
            if (saved == null) {
                Button(
                    enabled = !saving,
                    onClick = {
                        saving = true
                        vm.save { ok, msg ->
                            saving = false
                            Toast.makeText(ctx, msg, Toast.LENGTH_LONG).show()
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(if (saving) "Salvataggio…" else "💾  Salva in rubrica") }
                OutlinedButton(onClick = { vm.checkDuplicates() }, modifier = Modifier.fillMaxWidth()) {
                    Text("Ricontrolla duplicati")
                }
            } else {
                Text("✓ Salvato", color = MaterialTheme.colorScheme.primary)
                OutlinedButton(onClick = { openContact(saved) }, modifier = Modifier.fillMaxWidth()) { Text("Apri contatto") }
                Button(onClick = { vm.screen = Screen.HOME }, modifier = Modifier.fillMaxWidth()) { Text("Nuova scansione") }
            }
            Text("")
        }
    }
}

@Composable
private fun Field(label: String, value: String, singleLine: Boolean = true, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value, onValueChange = onChange, label = { Text(label) },
        singleLine = singleLine, modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun Section(title: String) {
    Text(title, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
}

private fun <T> List<T>.replace(i: Int, v: T): List<T> = mapIndexed { j, x -> if (j == i) v else x }
