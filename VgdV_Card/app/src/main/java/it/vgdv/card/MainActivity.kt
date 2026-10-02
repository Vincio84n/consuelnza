package it.vgdv.card

import android.Manifest
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.ui.graphics.Color
import it.vgdv.card.ui.HomeScreen
import it.vgdv.card.ui.ProcessingScreen
import it.vgdv.card.ui.ReviewScreen
import it.vgdv.card.ui.SettingsScreen

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()

    private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        vm.refreshContactsMeta()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        permissions.launch(arrayOf(Manifest.permission.READ_CONTACTS, Manifest.permission.WRITE_CONTACTS))

        setContent {
            val blue = Color(0xFF0D47A1)
            val scheme = if (isSystemInDarkTheme()) darkColorScheme(primary = Color(0xFF90CAF9))
            else lightColorScheme(primary = blue)
            MaterialTheme(colorScheme = scheme) {
                Surface {
                    BackHandler(enabled = vm.screen == Screen.SETTINGS || vm.screen == Screen.REVIEW) {
                        vm.screen = Screen.HOME
                    }
                    when (vm.screen) {
                        Screen.HOME -> HomeScreen(vm)
                        Screen.PROCESSING -> ProcessingScreen(vm.status)
                        Screen.REVIEW -> ReviewScreen(vm, openContact = { uri ->
                            startActivity(Intent(Intent.ACTION_VIEW, uri))
                        })
                        Screen.SETTINGS -> SettingsScreen(vm)
                    }
                }
            }
        }
    }
}
