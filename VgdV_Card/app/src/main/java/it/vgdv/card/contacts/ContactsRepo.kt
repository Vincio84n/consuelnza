package it.vgdv.card.contacts

import android.content.ContentProviderOperation
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.provider.ContactsContract
import android.provider.ContactsContract.CommonDataKinds
import android.provider.ContactsContract.Data
import android.provider.ContactsContract.Groups
import android.provider.ContactsContract.RawContacts
import it.vgdv.card.data.CardData
import it.vgdv.card.data.NameFormat

data class AccountInfo(val name: String, val type: String) {
    val label: String get() = if (name.isEmpty()) "Solo dispositivo" else "$name ($type)"
}

data class GroupInfo(val id: Long, val title: String)

class ContactsRepo(private val context: Context) {
    private val resolver get() = context.contentResolver

    /** Account che possiedono gruppi (tipicamente gli account Google). */
    fun accounts(): List<AccountInfo> {
        val out = linkedSetOf<AccountInfo>()
        resolver.query(
            Groups.CONTENT_URI, arrayOf(Groups.ACCOUNT_NAME, Groups.ACCOUNT_TYPE),
            "${Groups.DELETED}=0", null, null,
        )?.use { c ->
            while (c.moveToNext()) {
                val n = c.getString(0) ?: continue
                val t = c.getString(1) ?: continue
                out += AccountInfo(n, t)
            }
        }
        return out.toList()
    }

    /** Gruppi/etichette dell'account (esclusi quelli di sistema come "Preferiti"). */
    fun groups(account: AccountInfo?): List<GroupInfo> {
        if (account == null || account.name.isEmpty()) return emptyList()
        val out = mutableListOf<GroupInfo>()
        resolver.query(
            Groups.CONTENT_URI, arrayOf(Groups._ID, Groups.TITLE),
            "${Groups.DELETED}=0 AND ${Groups.SYSTEM_ID} IS NULL AND ${Groups.ACCOUNT_NAME}=? AND ${Groups.ACCOUNT_TYPE}=?",
            arrayOf(account.name, account.type), "${Groups.TITLE} COLLATE NOCASE",
        )?.use { c ->
            while (c.moveToNext()) {
                val title = c.getString(1) ?: continue
                out += GroupInfo(c.getLong(0), title)
            }
        }
        return out.distinctBy { it.title }
    }

    fun createGroup(title: String, account: AccountInfo): GroupInfo? {
        val values = ContentValues().apply {
            put(Groups.TITLE, title)
            put(Groups.ACCOUNT_NAME, account.name)
            put(Groups.ACCOUNT_TYPE, account.type)
            put(Groups.GROUP_VISIBLE, 1)
        }
        val uri = resolver.insert(Groups.CONTENT_URI, values) ?: return null
        return GroupInfo(uri.lastPathSegment!!.toLong(), title)
    }

    /** Contatti già presenti con stesso telefono o email. */
    fun findDuplicates(card: CardData): List<String> {
        val names = linkedSetOf<String>()
        for (p in card.phones) {
            val uri = Uri.withAppendedPath(ContactsContract.PhoneLookup.CONTENT_FILTER_URI, Uri.encode(p.number))
            resolver.query(uri, arrayOf(ContactsContract.PhoneLookup.DISPLAY_NAME), null, null, null)?.use { c ->
                while (c.moveToNext()) c.getString(0)?.let { names += "$it (tel. ${p.number})" }
            }
        }
        for (e in card.emails) {
            val uri = Uri.withAppendedPath(CommonDataKinds.Email.CONTENT_LOOKUP_URI, Uri.encode(e))
            resolver.query(uri, arrayOf(Data.DISPLAY_NAME), null, null, null)?.use { c ->
                while (c.moveToNext()) c.getString(0)?.let { names += "$it ($e)" }
            }
        }
        return names.toList()
    }

    fun displayName(card: CardData, format: NameFormat): String {
        val fl = listOf(card.firstName, card.lastName).filter { it.isNotBlank() }.joinToString(" ")
        val lf = listOf(card.lastName, card.firstName).filter { it.isNotBlank() }.joinToString(" ")
        val base = when (format) {
            NameFormat.LAST_FIRST -> lf
            NameFormat.FIRST_LAST_COMPANY -> if (card.company.isNotBlank()) "$fl (${card.company})".trim() else fl
            NameFormat.COMPANY_FIRST_LAST -> if (card.company.isNotBlank()) "${card.company} - $fl".trim(' ', '-') else fl
            NameFormat.FIRST_LAST -> fl
        }
        return base.ifBlank { card.company }
    }

    /** Salva il contatto in rubrica. Restituisce l'URI per aprirlo nell'app Contatti. */
    fun save(
        card: CardData,
        format: NameFormat,
        account: AccountInfo?,
        groupIds: Collection<Long>,
        note: String,
    ): Uri? {
        val ops = ArrayList<ContentProviderOperation>()
        val acc = account?.takeIf { it.name.isNotEmpty() }
        ops += ContentProviderOperation.newInsert(RawContacts.CONTENT_URI)
            .withValue(RawContacts.ACCOUNT_TYPE, acc?.type)
            .withValue(RawContacts.ACCOUNT_NAME, acc?.name)
            .build()

        fun data(mime: String) = ContentProviderOperation.newInsert(Data.CONTENT_URI)
            .withValueBackReference(Data.RAW_CONTACT_ID, 0)
            .withValue(Data.MIMETYPE, mime)

        ops += data(CommonDataKinds.StructuredName.CONTENT_ITEM_TYPE)
            .withValue(CommonDataKinds.StructuredName.DISPLAY_NAME, displayName(card, format))
            .withValue(CommonDataKinds.StructuredName.GIVEN_NAME, card.firstName.ifBlank { null })
            .withValue(CommonDataKinds.StructuredName.FAMILY_NAME, card.lastName.ifBlank { null })
            .build()

        if (card.company.isNotBlank() || card.jobTitle.isNotBlank()) {
            ops += data(CommonDataKinds.Organization.CONTENT_ITEM_TYPE)
                .withValue(CommonDataKinds.Organization.COMPANY, card.company.ifBlank { null })
                .withValue(CommonDataKinds.Organization.TITLE, card.jobTitle.ifBlank { null })
                .withValue(CommonDataKinds.Organization.TYPE, CommonDataKinds.Organization.TYPE_WORK)
                .build()
        }
        card.phones.filter { it.number.isNotBlank() }.forEach { p ->
            ops += data(CommonDataKinds.Phone.CONTENT_ITEM_TYPE)
                .withValue(CommonDataKinds.Phone.NUMBER, p.number)
                .withValue(CommonDataKinds.Phone.TYPE, p.type.androidType)
                .build()
        }
        card.emails.filter { it.isNotBlank() }.forEach { e ->
            ops += data(CommonDataKinds.Email.CONTENT_ITEM_TYPE)
                .withValue(CommonDataKinds.Email.ADDRESS, e)
                .withValue(CommonDataKinds.Email.TYPE, CommonDataKinds.Email.TYPE_WORK)
                .build()
        }
        if (card.website.isNotBlank()) {
            ops += data(CommonDataKinds.Website.CONTENT_ITEM_TYPE)
                .withValue(CommonDataKinds.Website.URL, card.website)
                .withValue(CommonDataKinds.Website.TYPE, CommonDataKinds.Website.TYPE_WORK)
                .build()
        }
        if (card.address.isNotBlank()) {
            ops += data(CommonDataKinds.StructuredPostal.CONTENT_ITEM_TYPE)
                .withValue(CommonDataKinds.StructuredPostal.FORMATTED_ADDRESS, card.address)
                .withValue(CommonDataKinds.StructuredPostal.TYPE, CommonDataKinds.StructuredPostal.TYPE_WORK)
                .build()
        }
        if (note.isNotBlank()) {
            ops += data(CommonDataKinds.Note.CONTENT_ITEM_TYPE)
                .withValue(CommonDataKinds.Note.NOTE, note)
                .build()
        }
        if (acc != null) {
            groupIds.forEach { gid ->
                ops += data(CommonDataKinds.GroupMembership.CONTENT_ITEM_TYPE)
                    .withValue(CommonDataKinds.GroupMembership.GROUP_ROW_ID, gid)
                    .build()
            }
        }

        val results = resolver.applyBatch(ContactsContract.AUTHORITY, ops)
        val rawUri = results.firstOrNull()?.uri ?: return null
        return RawContacts.getContactLookupUri(resolver, rawUri)
    }
}
