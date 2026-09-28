package com.ams.rfid.core

import java.io.IOException

/** 클론 결과. */
sealed class CloneResult {
    data object Success : CloneResult()
    data class Failure(val message: String, val tagLost: Boolean = false) : CloneResult()
}

/** CUID(마법) 카드 여부 판정 결과. */
sealed class CuidCheck {
    /** 블록 0 재기록 가능 → AMS용 클론에 사용할 수 있는 CUID/마법 카드. */
    data object Writable : CuidCheck()
    /** 블록 0 재기록 불가 → 일반 카드이거나 잠긴 카드. */
    data object NotWritable : CuidCheck()
    /** FF 키 인증 실패 → 먼저 포맷/초기화가 필요. */
    data object NeedsFormat : CuidCheck()
    data class Error(val message: String) : CuidCheck()
}

/**
 * 라이브러리에서 고른 덤프(원본 UID·유도 키 포함)를 빈 CUID 카드에 그대로 복제한다.
 *
 * 순수 로직만 담고 있으며 [MifareCard] 추상화 위에서 동작한다. 따라서 실제 NFC 하드웨어
 * 없이도 접근 규칙을 흉내 내는 가짜 카드로 동작을 검증할 수 있다.
 */
class TagCloner(private val ffKey: ByteArray = ByteArray(6) { 0xFF.toByte() }) {

    /** UID만 빠르게 읽는다. */
    fun readUid(card: MifareCard): ByteArray = card.uid

    /**
     * 현재 카드가 CUID(블록 0 재기록 가능) 카드인지 확인한다.
     * 원본 데이터를 그대로 다시 써서 내용은 바뀌지 않는다.
     */
    fun checkCuid(card: MifareCard): CuidCheck {
        return try {
            if (!card.authenticateSectorWithKeyA(0, ffKey)) {
                return CuidCheck.NeedsFormat
            }
            val original = card.readBlock(0)
            try {
                card.writeBlock(0, original)
                CuidCheck.Writable
            } catch (_: IOException) {
                CuidCheck.NotWritable
            }
        } catch (e: TagLostIoException) {
            CuidCheck.Error(e.message ?: "태그를 놓쳤습니다")
        } catch (e: Exception) {
            CuidCheck.Error(e.message ?: "알 수 없는 오류")
        }
    }

    /**
     * 덤프를 카드에 복제한다.
     * @param onProgress (완료 섹터 수, 전체 섹터 수) 콜백
     */
    fun clone(card: MifareCard, dump: TagDump, onProgress: (Int, Int) -> Unit = { _, _ -> }): CloneResult {
        val sectorCount = minOf(MifareCard.SECTOR_COUNT_1K, card.sectorCount)
        try {
            for (sector in 0 until sectorCount) {
                onProgress(sector, sectorCount)
                val target = dump.sectorKey(sector)
                val auth = authenticate(card, sector, target)
                    ?: return CloneResult.Failure("섹터 $sector 인증 실패 — 빈 CUID 카드가 맞는지 확인하세요")
                val alreadyKeyed = auth == AuthUsed.TARGET

                val start = card.sectorToBlock(sector)
                val count = card.blockCountInSector(sector)
                for (offset in 0 until count) {
                    val blockIndex = start + offset
                    val isTrailer = offset == count - 1
                    val data = dump.block(blockIndex)

                    if (isTrailer) {
                        // 이미 목표 키로 인증됐다면 trailer 키가 자리 잡은 것이므로 재기록하지 않는다.
                        if (alreadyKeyed) continue
                        writeOrFail(card, blockIndex, data)?.let { return it }
                    } else {
                        // 이미 같은 내용이면 건너뛴다 (NFC 왕복·마모 감소).
                        val current = runCatching { card.readBlock(blockIndex) }.getOrNull()
                        if (current != null && current.contentEquals(data)) continue
                        val fail = writeOrFail(card, blockIndex, data)
                        if (fail != null) {
                            // 블록 0은 UID/제조사 블록: CUID가 아니면 여기서 실패한다.
                            if (blockIndex == 0) {
                                return CloneResult.Failure(
                                    "블록 0(UID)을 쓸 수 없습니다. CUID/마법 카드가 아니거나 UID가 잠긴 카드입니다."
                                )
                            }
                            return fail
                        }
                    }
                }
            }
            onProgress(sectorCount, sectorCount)
            return CloneResult.Success
        } catch (e: TagLostIoException) {
            return CloneResult.Failure(e.message ?: "태그를 놓쳤습니다. 다시 대주세요.", tagLost = true)
        } catch (e: Exception) {
            return CloneResult.Failure(e.message ?: "알 수 없는 오류")
        }
    }

    /** 카드 내용이 덤프와 일치하는지 검증한다(키 바이트는 무시). */
    fun verify(card: MifareCard, dump: TagDump): CloneResult {
        val sectorCount = minOf(MifareCard.SECTOR_COUNT_1K, card.sectorCount)
        try {
            for (sector in 0 until sectorCount) {
                val target = dump.sectorKey(sector)
                if (authenticate(card, sector, target) == null) {
                    return CloneResult.Failure("검증: 섹터 $sector 인증 실패")
                }
                val start = card.sectorToBlock(sector)
                val count = card.blockCountInSector(sector)
                for (offset in 0 until count) {
                    val blockIndex = start + offset
                    val actual = card.readBlock(blockIndex)
                    val expected = dump.block(blockIndex)
                    if (!equivalent(blockIndex, expected, actual)) {
                        return CloneResult.Failure("검증: 블록 $blockIndex 불일치")
                    }
                }
            }
            return CloneResult.Success
        } catch (e: TagLostIoException) {
            return CloneResult.Failure(e.message ?: "태그를 놓쳤습니다.", tagLost = true)
        } catch (e: Exception) {
            return CloneResult.Failure(e.message ?: "알 수 없는 오류")
        }
    }

    /**
     * 전체 태그를 읽어 덤프로 만든다(기존 Bambu 태그 확인용).
     * @param keys UID로부터 유도한 섹터 키
     */
    fun readDump(card: MifareCard, keys: List<SectorKey>): TagDump? {
        val blocks = arrayOfNulls<ByteArray>(TagDump.BLOCKS)
        try {
            val sectorCount = minOf(MifareCard.SECTOR_COUNT_1K, card.sectorCount)
            for (sector in 0 until sectorCount) {
                val key = keys.getOrNull(sector) ?: continue
                val ok = card.authenticateSectorWithKeyA(sector, key.keyA) ||
                    card.authenticateSectorWithKeyB(sector, key.keyB)
                if (!ok) continue
                val start = card.sectorToBlock(sector)
                val count = card.blockCountInSector(sector)
                for (offset in 0 until count) {
                    val idx = start + offset
                    blocks[idx] = runCatching { card.readBlock(idx) }.getOrNull()
                }
            }
        } catch (_: Exception) {
            // 부분 읽기라도 반환한다.
        }
        if (blocks[0] == null) return null
        return TagDump.fromBlocks(blocks.toList())
    }

    private enum class AuthUsed { FF, TARGET }

    private fun authenticate(card: MifareCard, sector: Int, target: SectorKey): AuthUsed? {
        if (card.authenticateSectorWithKeyA(sector, ffKey) ||
            card.authenticateSectorWithKeyB(sector, ffKey)
        ) return AuthUsed.FF
        if (card.authenticateSectorWithKeyA(sector, target.keyA) ||
            card.authenticateSectorWithKeyB(sector, target.keyB)
        ) return AuthUsed.TARGET
        return null
    }

    private fun writeOrFail(card: MifareCard, blockIndex: Int, data: ByteArray): CloneResult.Failure? {
        return try {
            card.writeBlock(blockIndex, data)
            null
        } catch (e: TagLostIoException) {
            throw e
        } catch (e: IOException) {
            CloneResult.Failure("블록 $blockIndex 쓰기 실패: ${e.message}")
        }
    }

    /** trailer 블록에서는 키 6+6바이트를 제외하고 비교한다. */
    private fun equivalent(blockIndex: Int, expected: ByteArray, actual: ByteArray): Boolean {
        if (blockIndex % 4 != 3) return expected.contentEquals(actual)
        for (i in 6..9) {
            if (expected[i] != actual[i]) return false
        }
        return true
    }
}
