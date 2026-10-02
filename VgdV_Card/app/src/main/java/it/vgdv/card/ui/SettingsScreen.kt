package it.vgdv.card.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import it.vgdv.card.AppViewModel
import it.vgdv.card.Screen
import it.vgdv.card.contacts.AccountInfo
import it.vgdv.card.data.NameFormat
import it.vgdv.card.data.Provider

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(vm: AppViewModel) {
    val s = vm.settings
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("Impostazioni") },
            navigationIcon = { TextButton(onClick = { vm.screen = Screen.HOME; vm.refreshContactsMeta() }) { Text("←") } },
        )
    }) { pad ->
        Column(
            Modifier.padding(pad).padding(16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("Motore di analisi", style = MaterialTheme.typography.titleSmall)
            Picker(s.provider.label, Provider.entries, { it.label }, { vm.updateSettings(s.copy(provider = it)) })
            Text(
                "L'OCR avviene sempre sul telefono. Ai provider cloud viene inviato solo il testo letto, mai la foto.",
                style = MaterialTheme.typography.bodySmall,
            )

            when (s.provider) {
                Provider.GEMINI -> {
                    Secret("Chiave API Gemini (aistudio.google.com)", s.geminiKey) { vm.updateSettings(s.copy(geminiKey = it)) }
                    PasteKey { vm.updateSettings(s.copy(geminiKey = it)) }
                    Plain("Modello Gemini", s.geminiModel) { vm.updateSettings(s.copy(geminiModel = it)) }
                }
                Provider.NVIDIA -> {
                    Secret("Chiave API NVIDIA (nvapi-…)", s.nvidiaKey) { vm.updateSettings(s.copy(nvidiaKey = it)) }
                    PasteKey { vm.updateSettings(s.copy(nvidiaKey = it)) }
                    Plain("Modello", s.nvidiaModel) { vm.updateSettings(s.copy(nvidiaModel = it)) }
                    Plain("Base URL (OpenAI-compatibile)", s.nvidiaBaseUrl) { vm.updateSettings(s.copy(nvidiaBaseUrl = it)) }
                }
                Provider.OFFLINE -> Unit
            }
            Button(onClick = { vm.testConnection() }) { Text("Prova connessione") }
            if (vm.testResult.isNotBlank()) Text(vm.testResult, style = MaterialTheme.typography.bodySmall)

            Text("Rubrica di destinazione", style = MaterialTheme.typography.titleSmall)
            val options = vm.accounts + AccountInfo("", "")
            Picker(vm.currentAccount?.label ?: "Solo dispositivo", options, { it.label }, {
                vm.updateSettings(s.copy(accountName = it.name, accountType = it.type))
                vm.refreshContactsMeta()
            })
            Text(
                "I gruppi (es. Clienti, Fornitori) esistono solo sugli account Google: scegli il tuo account.",
                style = MaterialTheme.typography.bodySmall,
            )

            Text("Formato nome contatto", style = MaterialTheme.typography.titleSmall)
            Picker(s.nameFormat.label, NameFormat.entries, { it.label }, { vm.updateSettings(s.copy(nameFormat = it)) })

            Text("VgdV Card 0.2.0", style = MaterialTheme.typography.bodySmall)
        }
    }
}

/** Incolla la chiave dagli appunti con un tap (più comodo che digitarla). */
@Composable
private fun PasteKey(onKey: (String) -> Unit) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    androidx.compose.material3.OutlinedButton(onClick = {
        clipboard.getText()?.text?.trim()?.takeIf { it.isNotEmpty() }?.let(onKey)
    }) { Text("📋 Incolla chiave dagli appunti") }
}

@Composable
private fun Secret(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value, onValueChange = onChange, label = { Text(label) }, singleLine = true,
        visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun Plain(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value, onValueChange = onChange, label = { Text(label) }, singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
}
