package com.ams.rfid.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LibraryUpdateTest {

    @Test
    fun diffFindsAddedAndRemoved() {
        val d = LibraryUpdate.diff(
            current = listOf("PLA/PLA Basic/Black", "PLA/PLA Basic/Red"),
            incoming = listOf("PLA/PLA Basic/Black", "PLA/PLA Basic/Mint", "PETG/PETG HF/Blue"),
        )
        assertEquals(listOf("PLA/PLA Basic/Mint", "PETG/PETG HF/Blue"), d.added)
        assertEquals(listOf("PLA/PLA Basic/Red"), d.removed)
    }

    @Test
    fun newerWhenCommitDiffersAndGeneratedLater() {
        assertTrue(LibraryUpdate.isNewer("aaa", "2026-09-28T02:54:00Z", "bbb", "2026-10-05T03:17:00Z", 1))
    }

    @Test
    fun notNewerWhenSameCommit() {
        assertFalse(LibraryUpdate.isNewer("aaa", "2026-09-28T02:54:00Z", "aaa", "2026-10-05T03:17:00Z", 1))
    }

    @Test
    fun notNewerWhenRemoteIsOlder() {
        // 앱에 내장된 DB가 게시된 DB보다 최신인 경우 (APK가 더 나중에 빌드됨)
        assertFalse(LibraryUpdate.isNewer("aaa", "2026-10-06T00:00:00Z", "bbb", "2026-10-05T03:17:00Z", 1))
    }

    @Test
    fun notNewerWhenFormatUnsupported() {
        assertFalse(LibraryUpdate.isNewer("aaa", "2026-09-28T02:54:00Z", "bbb", "2026-10-05T03:17:00Z", 2))
    }

    @Test
    fun notNewerWhenRemoteCommitEmpty() {
        assertFalse(LibraryUpdate.isNewer("aaa", "2026-09-28T02:54:00Z", "", "2026-10-05T03:17:00Z", 1))
    }

    @Test
    fun peekGeneratedReadsHeader() {
        val head = """{"source":"x","format":1,"commit":"abc","generated":"2026-09-28T11:05:05Z","entries":[{"cat"""
        assertEquals("2026-09-28T11:05:05Z", LibraryUpdate.peekGenerated(head))
        assertNull(LibraryUpdate.peekGenerated("""{"entries":[]}"""))
    }

    @Test
    fun displayNameShowsMaterialAndColor() {
        assertEquals("PLA Basic · Black", LibraryUpdate.displayName("PLA/PLA Basic/Black"))
        assertEquals("odd", LibraryUpdate.displayName("odd"))
    }
}
