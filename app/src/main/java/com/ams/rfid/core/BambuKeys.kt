package com.ams.rfid.core

import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Bambu Lab MIFARE Classic 태그의 섹터 키를 UID로부터 유도한다.
 *
 * 알고리즘은 공개된 Bambu Research Group / queengooborg 문서의 것과 동일하다:
 * HKDF-SHA256(고정 salt, ikm=UID)로 PRK를 얻고, info="RFID-A\0"/"RFID-B\0"으로
 * 각각 16섹터 × 6바이트 키를 확장한다. 태그마다 UID가 다르면 키도 전부 달라진다.
 */
object BambuKeys {
    private val SALT = byteArrayOf(
        0x9a.toByte(), 0x75, 0x9c.toByte(), 0xf2.toByte(),
        0xc4.toByte(), 0xf7.toByte(), 0xca.toByte(), 0xff.toByte(),
        0x22, 0x2c, 0xb9.toByte(), 0x76,
        0x9b.toByte(), 0x41, 0xbc.toByte(), 0x96.toByte(),
    )
    private val INFO_A = "RFID-A\u0000".toByteArray(Charsets.US_ASCII)
    private val INFO_B = "RFID-B\u0000".toByteArray(Charsets.US_ASCII)

    private const val SECTOR_COUNT = 16
    private const val KEY_LENGTH = 6

    /** 각 섹터의 (KeyA, KeyB) 쌍 16개를 반환한다. */
    fun derive(uid: ByteArray): List<SectorKey> {
        val keysA = expand(uid, INFO_A)
        val keysB = expand(uid, INFO_B)
        return (0 until SECTOR_COUNT).map { SectorKey(keysA[it], keysB[it]) }
    }

    private fun expand(uid: ByteArray, info: ByteArray): List<ByteArray> {
        val prk = hmac(SALT, uid)
        val length = KEY_LENGTH * SECTOR_COUNT
        val out = ArrayList<Byte>(length + 32)
        var t = ByteArray(0)
        var counter = 1
        while (out.size < length) {
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(prk, "HmacSHA256"))
            mac.update(t)
            mac.update(info)
            mac.update(counter.toByte())
            t = mac.doFinal()
            for (b in t) out.add(b)
            counter++
        }
        val okm = out.toByteArray()
        return (0 until SECTOR_COUNT).map { okm.copyOfRange(it * KEY_LENGTH, it * KEY_LENGTH + KEY_LENGTH) }
    }

    private fun hmac(key: ByteArray, data: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return mac.doFinal(data)
    }
}

/** 한 섹터의 KeyA/KeyB. */
data class SectorKey(val keyA: ByteArray, val keyB: ByteArray) {
    override fun equals(other: Any?): Boolean =
        other is SectorKey && keyA.contentEquals(other.keyA) && keyB.contentEquals(other.keyB)

    override fun hashCode(): Int = keyA.contentHashCode() * 31 + keyB.contentHashCode()
}
