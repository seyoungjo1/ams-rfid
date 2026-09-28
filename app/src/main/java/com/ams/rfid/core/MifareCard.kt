package com.ams.rfid.core

import java.io.IOException

/**
 * MIFARE Classic 1K 카드에 대한 순수(안드로이드 비의존) 추상화.
 *
 * 실제 앱에서는 android.nfc.tech.MifareClassic 을 감싸는 어댑터가 이 인터페이스를 구현하고,
 * 단위 테스트에서는 접근 규칙을 흉내 내는 가짜 카드가 구현한다. 덕분에 클론/검증/포맷 등
 * 핵심 로직을 실제 하드웨어 없이 JVM에서 검증할 수 있다.
 */
interface MifareCard {
    /** 카드 UID (제조사 블록 앞 4바이트). */
    val uid: ByteArray

    /** 섹터 수. 표준 1K 카드는 16. */
    val sectorCount: Int

    /** 총 블록 수. 표준 1K 카드는 64. */
    val blockCount: Int

    fun connect()
    fun close()

    fun sectorToBlock(sector: Int): Int = sector * BLOCKS_PER_SECTOR
    fun blockCountInSector(sector: Int): Int = BLOCKS_PER_SECTOR

    fun authenticateSectorWithKeyA(sector: Int, key: ByteArray): Boolean
    fun authenticateSectorWithKeyB(sector: Int, key: ByteArray): Boolean

    @Throws(IOException::class)
    fun readBlock(block: Int): ByteArray

    @Throws(IOException::class)
    fun writeBlock(block: Int, data: ByteArray)

    companion object {
        const val BLOCKS_PER_SECTOR = 4
        const val BYTES_PER_BLOCK = 16
        const val SECTOR_COUNT_1K = 16
        const val BLOCK_COUNT_1K = 64
    }
}

/** 태그가 사라졌거나 통신이 끊긴 경우. 사용자에게 "다시 태그를 대주세요"로 안내한다. */
class TagLostIoException(message: String) : IOException(message)
