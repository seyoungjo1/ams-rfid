package com.ams.rfid.nfc

import android.nfc.Tag
import android.nfc.TagLostException
import android.nfc.tech.MifareClassic
import com.ams.rfid.core.MifareCard
import com.ams.rfid.core.TagLostIoException
import java.io.IOException

/**
 * android.nfc.tech.MifareClassic 을 [MifareCard] 로 감싸는 어댑터.
 * 코어 로직은 이 인터페이스에만 의존하므로 하드웨어와 분리되어 테스트 가능하다.
 */
class AndroidMifareCard(tag: Tag) : MifareCard {

    private val mifare: MifareClassic = MifareClassic.get(tag)
        ?: throw IOException("MIFARE_UNSUPPORTED")

    override val uid: ByteArray = tag.id ?: ByteArray(0)
    override val sectorCount: Int get() = mifare.sectorCount
    override val blockCount: Int get() = mifare.blockCount

    override fun connect() {
        mifare.connect()
        // 통신 타임아웃을 넉넉히 잡아 저가 카드에서의 간헐적 실패를 줄인다.
        runCatching { mifare.timeout = 1500 }
    }

    override fun close() {
        runCatching { mifare.close() }
    }

    override fun sectorToBlock(sector: Int): Int = mifare.sectorToBlock(sector)
    override fun blockCountInSector(sector: Int): Int = mifare.getBlockCountInSector(sector)

    override fun authenticateSectorWithKeyA(sector: Int, key: ByteArray): Boolean =
        wrap { mifare.authenticateSectorWithKeyA(sector, key) }

    override fun authenticateSectorWithKeyB(sector: Int, key: ByteArray): Boolean =
        wrap { mifare.authenticateSectorWithKeyB(sector, key) }

    override fun readBlock(block: Int): ByteArray = wrap {
        val raw = mifare.readBlock(block)
        if (raw.size >= 16) raw.copyOf(16) else throw IOException("블록 길이 오류(${raw.size})")
    }

    override fun writeBlock(block: Int, data: ByteArray) = wrap {
        mifare.writeBlock(block, data)
    }

    private inline fun <T> wrap(body: () -> T): T {
        try {
            return body()
        } catch (e: TagLostException) {
            throw TagLostIoException(e.message ?: "태그를 놓쳤습니다")
        }
    }
}
