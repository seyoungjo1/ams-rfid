package com.ams.rfid.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DumpFileTest {

    private fun sampleBytes(): ByteArray =
        javaClass.getResourceAsStream("/sample_tag.bin")!!.readBytes()

    private fun ok(bytes: ByteArray): DumpFile.Result.Ok {
        val r = DumpFile.parse(bytes)
        assertTrue("파싱 실패: $r", r is DumpFile.Result.Ok)
        return r as DumpFile.Result.Ok
    }

    @Test
    fun parsesRawBin() {
        assertEquals("02034E6D", ok(sampleBytes()).dump.uidHex)
    }

    @Test
    fun parses72BlockBinByTruncating() {
        // fm11rf08s 복구 결과(1152바이트)처럼 뒤에 8블록이 더 붙은 경우: 앞 1024바이트만 쓴다.
        val padded = sampleBytes() + ByteArray(128) { 0x11 }
        assertEquals(1152, padded.size)
        val result = ok(padded)
        assertEquals("02034E6D", result.dump.uidHex)
        assertTrue(result.format.contains("72"))
    }

    @Test
    fun parsesProxmarkJson() {
        val blocks = TagDump.of(sampleBytes())
        val sb = StringBuilder("{\"Created\":\"proxmark3\",\"blocks\":{")
        for (i in 0 until 64) {
            if (i > 0) sb.append(",")
            sb.append("\"$i\":\"").append(blocks.block(i).toHex()).append("\"")
        }
        sb.append("}}")
        val result = ok(sb.toString().toByteArray())
        assertEquals("JSON", result.format)
        assertTrue(result.dump.bytes.contentEquals(blocks.bytes))
    }

    @Test
    fun parsesFlipperNfc() {
        val blocks = TagDump.of(sampleBytes())
        val sb = StringBuilder("Filetype: Flipper NFC device\nVersion: 4\nDevice type: Mifare Classic\n")
        for (i in 0 until 64) {
            val hex = blocks.block(i).toHex().chunked(2).joinToString(" ")
            sb.append("Block ").append(i).append(": ").append(hex).append("\n")
        }
        val result = ok(sb.toString().toByteArray())
        assertEquals("Flipper NFC", result.format)
        assertEquals("02034E6D", result.dump.uidHex)
    }

    @Test
    fun rejectsTooShort() {
        assertTrue(DumpFile.parse(ByteArray(512)) is DumpFile.Result.Error)
    }

    @Test
    fun handlesQuestionMarkPlaceholders() {
        val blocks = TagDump.of(sampleBytes())
        val sb = StringBuilder("{\"blocks\":{")
        for (i in 0 until 64) {
            if (i > 0) sb.append(",")
            // 블록 4 의 앞 2바이트를 ?? 로 흐려 둔 경우에도 00 으로 채워 읽혀야 한다.
            val hex = if (i == 4) "????" + blocks.block(i).toHex().substring(4) else blocks.block(i).toHex()
            sb.append("\"$i\":\"").append(hex).append("\"")
        }
        sb.append("}}")
        assertEquals(0, ok(sb.toString().toByteArray()).dump.block(4)[0].toInt())
    }
}
