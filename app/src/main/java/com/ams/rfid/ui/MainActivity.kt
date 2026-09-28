package com.ams.rfid.ui

import android.nfc.NfcAdapter
import android.nfc.Tag
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.lifecycle.lifecycleScope
import com.ams.rfid.R
import com.ams.rfid.core.MifareCard
import com.ams.rfid.nfc.AndroidMifareCard
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity(), NfcAdapter.ReaderCallback {

    private val viewModel: MainViewModel by viewModels()
    private var nfcAdapter: NfcAdapter? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        nfcAdapter = NfcAdapter.getDefaultAdapter(this)
        viewModel.loadLibrary()
        setContent {
            AmsRfidTheme {
                AppRoot(viewModel)
            }
        }
        if (nfcAdapter == null) {
            Toast.makeText(this, R.string.nfc_unsupported, Toast.LENGTH_LONG).show()
        }
    }

    override fun onResume() {
        super.onResume()
        val adapter = nfcAdapter ?: return
        if (!adapter.isEnabled) {
            Toast.makeText(this, R.string.nfc_disabled, Toast.LENGTH_LONG).show()
            return
        }
        // 리더 모드: 앱이 포그라운드일 때만 태그를 독점 처리한다. NDEF 검사·재생음은 끈다.
        val flags = NfcAdapter.FLAG_READER_NFC_A or
            NfcAdapter.FLAG_READER_NFC_B or
            NfcAdapter.FLAG_READER_SKIP_NDEF_CHECK or
            NfcAdapter.FLAG_READER_NO_PLATFORM_SOUNDS
        val extras = android.os.Bundle().apply {
            putInt(NfcAdapter.EXTRA_READER_PRESENCE_CHECK_DELAY, 250)
        }
        adapter.enableReaderMode(this, this, flags, extras)
    }

    override fun onPause() {
        super.onPause()
        nfcAdapter?.disableReaderMode(this)
    }

    /** NFC 시스템 스레드에서 호출된다. */
    override fun onTagDiscovered(tag: Tag) {
        val card: MifareCard = try {
            AndroidMifareCard(tag)
        } catch (e: Exception) {
            viewModel.reportNotMifare()
            return
        }
        // 콜백 스레드에서 그대로 실행해도 되지만, 코루틴(IO)로 넘겨 안전하게 처리한다.
        lifecycleScope.launch(Dispatchers.IO) {
            viewModel.executeOnCard(card)
        }
    }
}
