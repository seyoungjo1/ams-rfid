package com.ams.rfid.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CoreTest {

    private fun sampleDump(): TagDump {
        val bytes = javaClass.getResourceAsStream("/sample_tag.bin")!!.readBytes()
        return TagDump.of(bytes)
    }

    @Test
    fun keyDerivationMatchesStoredTrailerKeys() {
        val dump = sampleDump()
        val derived = BambuKeys.derive(dump.uid)
        for (sector in 0 until 16) {
            val stored = dump.sectorKey(sector)
            assertTrue(
                "섹터 $sector KeyA 유도 불일치",
                stored.keyA.contentEquals(derived[sector].keyA),
            )
            assertTrue(
                "섹터 $sector KeyB 유도 불일치",
                stored.keyB.contentEquals(derived[sector].keyB),
            )
        }
    }

    @Test
    fun knownUidDerivesKnownKeys() {
        // deriveKeys.py 로 UID 02034E6D 를 계산한 값과 대조 (섹터 0)
        val keys = BambuKeys.derive("02034E6D".hexToBytes())
        assertEquals("A8A4B07BEEF5", keys[0].keyA.toHex())
        assertEquals("215D0FCCEC59", keys[0].keyB.toHex())
    }

    @Test
    fun dumpValidationPasses() {
        assertTrue(DumpValidator.validate(sampleDump()).ok)
    }

    @Test
    fun filamentParsesBlackPla() {
        val info = FilamentInfo.parse(sampleDump())
        assertEquals("02034E6D", info.uid)
        assertEquals("PLA", info.filamentType)
        assertTrue("색상 코드 형식", info.colorHex.startsWith("#"))
        assertTrue("무게가 양수", info.spoolWeightGram > 0)
        assertTrue("노즐 최고온도 범위", info.maxHotendC in 150..350)
    }

    @Test
    fun cloneToBlankCuidCardThenVerify() {
        val dump = sampleDump()
        val card = FakeMifareCard.blank(dump.uid, magic = true)
        val cloner = TagCloner()

        val result = cloner.clone(card, dump)
        assertTrue("클론 성공해야 함: $result", result is CloneResult.Success)

        // trailer 키가 유도 키로 바뀌었는지: 이제 FF로는 인증 실패해야 한다.
        val ff = ByteArray(6) { 0xFF.toByte() }
        assertFalse(card.authenticateSectorWithKeyA(1, ff))

        val verify = cloner.verify(card, dump)
        assertTrue("검증 통과해야 함: $verify", verify is CloneResult.Success)

        // 데이터 블록이 원본과 동일한지 직접 확인
        val written = card.snapshot()
        for (b in intArrayOf(0, 1, 2, 4, 5, 6, 12)) {
            assertTrue(
                "블록 $b 내용 일치",
                written.copyOfRange(b * 16, b * 16 + 16).contentEquals(dump.block(b)),
            )
        }
    }

    @Test
    fun cloneIsIdempotent() {
        val dump = sampleDump()
        val card = FakeMifareCard.blank(dump.uid, magic = true)
        val cloner = TagCloner()
        assertTrue(cloner.clone(card, dump) is CloneResult.Success)
        // 두 번째 클론도 성공(이미 기록된 섹터는 건너뜀)
        assertTrue(cloner.clone(card, dump) is CloneResult.Success)
        assertTrue(cloner.verify(card, dump) is CloneResult.Success)
    }

    @Test
    fun cloneFailsOnNonMagicCard() {
        val dump = sampleDump()
        // magic=false: 블록 0 쓰기 금지 → 일반 카드 시뮬레이션
        val card = FakeMifareCard.blank(dump.uid, magic = false)
        val result = cloner().clone(card, dump)
        assertTrue("일반 카드는 실패해야 함", result is CloneResult.Failure)
        assertTrue(
            "블록 0 관련 안내여야 함",
            (result as CloneResult.Failure).message.contains("블록 0"),
        )
    }

    @Test
    fun checkCuidDetectsMagic() {
        val dump = sampleDump()
        assertEquals(CuidCheck.Writable, cloner().checkCuid(FakeMifareCard.blank(dump.uid, magic = true)))
        assertEquals(CuidCheck.NotWritable, cloner().checkCuid(FakeMifareCard.blank(dump.uid, magic = false)))
    }

    @Test
    fun readDumpRoundTrip() {
        val dump = sampleDump()
        val card = FakeMifareCard.blank(dump.uid, magic = true)
        val cloner = cloner()
        assertTrue(cloner.clone(card, dump) is CloneResult.Success)
        val readBack = cloner.readDump(card, BambuKeys.derive(dump.uid))
        assertNotNull(readBack)
        assertEquals(dump.uidHex, readBack!!.uidHex)
        assertEquals(
            FilamentInfo.parse(dump).filamentType,
            FilamentInfo.parse(readBack).filamentType,
        )
    }

    private fun cloner() = TagCloner()
}
