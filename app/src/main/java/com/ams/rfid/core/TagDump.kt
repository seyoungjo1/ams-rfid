package com.ams.rfid.core

/**
 * MIFARE Classic 1K 태그의 전체 덤프(64블록 × 16바이트 = 1024바이트).
 */
class TagDump private constructor(private val data: ByteArray) {

    init {
        require(data.size == SIZE) { "덤프 크기는 ${SIZE}바이트여야 합니다 (실제 ${data.size})" }
    }

    val bytes: ByteArray get() = data.copyOf()

    /** UID 4바이트 (제조사 블록 0의 앞 4바이트). */
    val uid: ByteArray get() = data.copyOfRange(0, 4)

    val uidHex: String get() = uid.toHex()

    fun block(index: Int): ByteArray {
        require(index in 0 until BLOCKS) { "블록 인덱스 범위 초과: $index" }
        val start = index * BLOCK
        return data.copyOfRange(start, start + BLOCK)
    }

    /** 섹터 trailer(마지막 블록)에서 KeyA/KeyB를 추출한다. */
    fun sectorKey(sector: Int): SectorKey {
        val trailer = block(sector * 4 + 3)
        return SectorKey(trailer.copyOfRange(0, 6), trailer.copyOfRange(10, 16))
    }

    companion object {
        const val BLOCK = 16
        const val BLOCKS = 64
        const val SIZE = BLOCK * BLOCKS

        fun of(bytes: ByteArray): TagDump {
            require(bytes.size >= SIZE) {
                "MIFARE 1K 덤프가 아닙니다 (수신 ${bytes.size}바이트, 필요 $SIZE)"
            }
            return TagDump(bytes.copyOf(SIZE))
        }

        /** 블록 리스트로부터 덤프를 만든다. null 블록은 0으로 채운다. */
        fun fromBlocks(blocks: List<ByteArray?>): TagDump {
            val out = ByteArray(SIZE)
            for (i in 0 until BLOCKS) {
                val b = blocks.getOrNull(i) ?: continue
                val n = minOf(BLOCK, b.size)
                System.arraycopy(b, 0, out, i * BLOCK, n)
            }
            return TagDump(out)
        }
    }
}

/**
 * 덤프의 유효성 검사 결과. 치명적 문제가 있으면 [ok] = false.
 */
data class DumpValidation(val ok: Boolean, val reason: String) {
    companion object {
        val VALID = DumpValidation(true, "")
    }
}

object DumpValidator {
    /** UID BCC, 필수 블록 존재, 유도 키 일치 여부를 검사한다. */
    fun validate(dump: TagDump): DumpValidation {
        val b0 = dump.block(0)
        val bcc = b0[0].toInt() xor b0[1].toInt() xor b0[2].toInt() xor b0[3].toInt()
        if ((bcc and 0xFF) != (b0[4].toInt() and 0xFF)) {
            return DumpValidation(false, "UID 체크바이트(BCC) 불일치")
        }
        for (b in intArrayOf(1, 2, 4, 5)) {
            if (dump.block(b).all { it == 0.toByte() }) {
                return DumpValidation(false, "필수 블록 $b 이(가) 비어 있음")
            }
        }
        val derived = BambuKeys.derive(dump.uid)
        for (sector in 0 until 16) {
            val stored = dump.sectorKey(sector)
            val expected = derived[sector]
            val keyABlank = stored.keyA.all { it == 0.toByte() } || stored.keyA.all { it == 0xFF.toByte() }
            if (!keyABlank && !stored.keyA.contentEquals(expected.keyA)) {
                return DumpValidation(false, "섹터 $sector KeyA 가 UID 유도 키와 다름")
            }
        }
        return DumpValidation.VALID
    }
}

fun ByteArray.toHex(): String = joinToString("") { "%02X".format(it) }

fun String.hexToBytes(): ByteArray {
    val clean = filter { !it.isWhitespace() }
    require(clean.length % 2 == 0) { "16진수 길이가 홀수입니다" }
    return ByteArray(clean.length / 2) {
        clean.substring(it * 2, it * 2 + 2).toInt(16).toByte()
    }
}
