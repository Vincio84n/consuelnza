package it.vgdv.card

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build

/** Versione installata e registro delle modifiche (assets/CHANGELOG.md). */
object AppInfo {
    fun versionName(ctx: Context): String = packageInfo(ctx).versionName ?: "?"

    @Suppress("DEPRECATION")
    fun versionCode(ctx: Context): Long {
        val p = packageInfo(ctx)
        return if (Build.VERSION.SDK_INT >= 28) p.longVersionCode else p.versionCode.toLong()
    }

    fun changelog(ctx: Context): String =
        runCatching { ctx.assets.open("CHANGELOG.md").bufferedReader().use { it.readText() } }.getOrDefault("")

    /** Solo le note della versione più recente (primo blocco "## "). */
    fun latestNotes(ctx: Context): String =
        changelog(ctx).split(Regex("(?m)^## ")).firstOrNull { it.isNotBlank() }?.let { "## $it".trim() } ?: ""

    private fun packageInfo(ctx: Context) = ctx.packageManager.getPackageInfo(ctx.packageName, PackageManager.GET_META_DATA)
}
