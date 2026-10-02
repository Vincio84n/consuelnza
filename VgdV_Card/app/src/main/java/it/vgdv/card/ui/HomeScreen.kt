package it.vgdv.card.ui

import android.app.Activity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import com.google.mlkit.vision.documentscanner.GmsDocumentScanning
import com.google.mlkit.vision.documentscanner.GmsDocumentScanningResult
import it.vgdv.card.AppViewModel
import it.vgdv.card.Screen
import it.vgdv.card.data.Provider

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(vm: AppViewModel) {
    val activity = LocalContext.current as Activity
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) { r ->
        if (r.resultCode == Activity.RESULT_OK) {
            val pages = GmsDocumentScanningResult.fromActivityResultIntent(r.data)?.pages.orEmpty()
            vm.onScanned(pages.map { it.imageUri })
        }
    }

    fun startScan() {
        val options = GmsDocumentScannerOptions.Builder()
            .setGalleryImportAllowed(true)
            .setPageLimit(2) // fronte + retro
            .setResultFormats(GmsDocumentScannerOptions.RESULT_FORMAT_JPEG)
            .setScannerMode(GmsDocumentScannerOptions.SCANNER_MODE_FULL)
            .build()
        GmsDocumentScanning.getClient(options).getStartScanIntent(activity)
            .addOnSuccessListener { launcher.launch(IntentSenderRequest.Builder(it).build()) }
            .addOnFailureListener { vm.status = "Scanner non disponibile: ${it.message}" }
    }

    val s = vm.settings
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("VgdV Card") },
            actions = {
                IconButton(onClick = { vm.refreshContactsMeta(); vm.screen = Screen.SETTINGS }) {
                    Icon(Icons.Default.Settings, contentDescription = "Impostazioni")
                }
            },
        )
    }) { pad ->
        Column(
            Modifier.padding(pad).padding(20.dp).fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(12.dp))
            Button(onClick = { startScan() }, modifier = Modifier.fillMaxWidth().height(72.dp)) {
                Text("📷  Scansiona biglietto", style = MaterialTheme.typography.titleMedium)
            }
            OutlinedTextField(
                value = s.currentEvent,
                onValueChange = { vm.updateSettings(s.copy(currentEvent = it)) },
                label = { Text("Evento / luogo corrente (va nelle note)") },
                placeholder = { Text("es. Fiera Milano, cena Rotary…") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                "Analisi: ${s.provider.label}\nRubrica: ${vm.currentAccount?.label ?: "Solo dispositivo"}\n" +
                    "Formato nome: ${s.nameFormat.label}",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.fillMaxWidth(),
            )
            val missingKey = (s.provider == Provider.GEMINI && s.geminiKey.isBlank()) ||
                (s.provider == Provider.NVIDIA && s.nvidiaKey.isBlank())
            if (missingKey) {
                Text(
                    "⚠ Chiave API non impostata: verrà usato il parser offline. Configurala nelle impostazioni.",
                    color = MaterialTheme.colorScheme.error,
                )
            }
            if (vm.status.isNotBlank()) Text(vm.status, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
fun ProcessingScreen(status: String) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        androidx.compose.material3.CircularProgressIndicator()
        Spacer(Modifier.height(16.dp))
        Text(status)
    }
}
