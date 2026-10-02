package it.vgdv.card

import android.content.Context
import android.net.Uri
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.tasks.await

/** OCR on-device con ML Kit: nessun dato lascia il telefono in questa fase. */
object Ocr {
    suspend fun read(context: Context, pages: List<Uri>): String {
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        try {
            return pages.mapIndexed { i, uri ->
                val text = recognizer.process(InputImage.fromFilePath(context, uri)).await().text
                if (pages.size > 1) "[${if (i == 0) "Fronte" else "Retro"}]\n$text" else text
            }.joinToString("\n\n")
        } finally {
            recognizer.close()
        }
    }
}
