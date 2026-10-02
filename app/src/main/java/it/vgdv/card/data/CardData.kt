package it.vgdv.card.data

import android.provider.ContactsContract.CommonDataKinds.Phone

enum class PhoneType(val label: String, val androidType: Int) {
    MOBILE("Cellulare", Phone.TYPE_MOBILE),
    WORK("Lavoro", Phone.TYPE_WORK),
    MAIN("Centralino", Phone.TYPE_MAIN),
    FAX("Fax", Phone.TYPE_FAX_WORK),
    HOME("Casa", Phone.TYPE_HOME),
    OTHER("Altro", Phone.TYPE_OTHER);

    companion object {
        fun parse(value: String?): PhoneType =
            entries.firstOrNull { it.name.equals(value?.trim(), ignoreCase = true) } ?: WORK
    }
}

data class PhoneEntry(val number: String, val type: PhoneType)

data class CardData(
    val firstName: String = "",
    val lastName: String = "",
    val company: String = "",
    val jobTitle: String = "",
    val phones: List<PhoneEntry> = emptyList(),
    val emails: List<String> = emptyList(),
    val website: String = "",
    val address: String = "",
    val suggestedGroups: List<String> = emptyList(),
    val summary: String = "",
)
