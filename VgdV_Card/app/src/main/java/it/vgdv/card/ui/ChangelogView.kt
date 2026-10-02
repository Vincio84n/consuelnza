package it.vgdv.card.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Mostra il changelog markdown semplice: "## titolo" e righe "- voce". */
@Composable
fun ChangelogView(markdown: String) {
    Column {
        markdown.lines().forEach { line ->
            when {
                line.startsWith("## ") -> Text(
                    line.removePrefix("## "),
                    style = MaterialTheme.typography.titleSmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(top = 10.dp, bottom = 2.dp),
                )
                line.startsWith("- ") -> Text("•  " + line.removePrefix("- "), style = MaterialTheme.typography.bodySmall)
                line.isNotBlank() -> Text(line, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
