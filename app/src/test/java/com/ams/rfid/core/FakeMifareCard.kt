package com.ams.rfid.core

import java.io.IOException

/**
 * 접근 규칙을 흉내 내는 가짜 MIFARE Classic 1K 카드. 단위 테스트 전용.
 *
 * 모델링하는 규칙:
 *  - 블록을 읽고 쓰려면 먼저 해당 섹터를 현재 유효한 KeyA/KeyB로 인증해야 한다.
 *  - trailer(각 섹터 마지막 블록)를 쓰면 그 섹터의 KeyA/KeyB/접근바이트가 바뀐다.
 *    → 이후에는 새 키로만 인증되므로, "trailer는 마지막에 쓰고 다음엔 유도 키로 재인증"
 *      하는 클론 로직을 실제로 검증할 수 있다.
 *  - 블록 0(제조사/UID 블록)은 magic(=CUID)일 때만 쓸 수 있고, 아니면 IOException.
 */
class FakeMifareCard(
    initial: ByteArray,
    private val magic: Boolean = true,
) : MifareCard {

    private val store: ByteArray = initial.copyOf(TagDump.SIZE)
    private var authedSector: Int = -1

    override val uid: ByteArray get() = store.copyOfRange(0, 4)
    override val sectorCount: Int = 16
    override val blockCount: Int = 64

    override fun connect() {}
    override fun close() {}

    private fun trailer(sector: Int): ByteArray {
        val idx = (sector * 4 + 3) * 16
        return store.copyOfRange(idx, idx + 16)
    }

    private fun currentKeyA(sector: Int) = trailer(sector).copyOfRange(0, 6)
    private fun currentKeyB(sector: Int) = trailer(sector).copyOfRange(10, 16)

    override fun authenticateSectorWithKeyA(sector: Int, key: ByteArray): Boolean {
        val ok = key.contentEquals(currentKeyA(sector))
        if (ok) authedSector = sector
        return ok
    }

    override fun authenticateSectorWithKeyB(sector: Int, key: ByteArray): Boolean {
        val ok = key.contentEquals(currentKeyB(sector))
        if (ok) authedSector = sector
        return ok
    }

    override fun readBlock(block: Int): ByteArray {
        requireAuthed(block)
        val start = block * 16
        return store.copyOfRange(start, start + 16)
    }

    override fun writeBlock(block: Int, data: ByteArray) {
        require(data.size == 16) { "블록은 16바이트여야 합니다" }
        requireAuthed(block)
        if (block == 0 && !magic) {
            throw IOException("블록 0은 쓰기 금지(일반 카드)")
        }
        System.arraycopy(data, 0, store, block * 16, 16)
    }

    private fun requireAuthed(block: Int) {
        val sector = block / 4
        if (authedSector != sector) {
            throw IOException("섹터 $sector 미인증 상태에서 블록 $block 접근")
        }
    }

    fun snapshot(): ByteArray = store.copyOf()

    companion object {
        /** 공장 출하(FF 키, 기본 접근바이트) 상태의 빈 1K 카드. */
        fun blank(uid: ByteArray, magic: Boolean = true): FakeMifareCard {
            val data = ByteArray(TagDump.SIZE)
            // 블록 0: UID + BCC + SAK/ATQA 흉내
            System.arraycopy(uid, 0, data, 0, 4)
            data[4] = (uid[0].toInt() xor uid[1].toInt() xor uid[2].toInt() xor uid[3].toInt()).toByte()
            data[5] = 0x08
            // 모든 trailer를 FF 키 + 기본 접근바이트(FF078069)로 채운다.
            val access = "FF078069".hexToBytes()
            for (sector in 0 until 16) {
                val t = (sector * 4 + 3) * 16
                for (i in 0 until 6) data[t + i] = 0xFF.toByte()
                System.arraycopy(access, 0, data, t + 6, 4)
                for (i in 10 until 16) data[t + i] = 0xFF.toByte()
            }
            return FakeMifareCard(data, magic)
        }
    }
}
