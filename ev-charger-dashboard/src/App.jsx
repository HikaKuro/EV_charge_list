import { useState, useEffect, useMemo } from 'react'
import { Calendar, MapPin, Zap, Search, Loader2, RefreshCw, AlertCircle, Wrench } from 'lucide-react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Leafletのデフォルトアイコンの問題を修正（ローカルファイルを使用）
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: '/leaflet-images/marker-icon-2x.png',
  iconUrl: '/leaflet-images/marker-icon.png',
  shadowUrl: '/leaflet-images/marker-shadow.png',
})

function App() {
  const [data, setData] = useState([])
  const [filteredData, setFilteredData] = useState([])
  const [loading, setLoading] = useState(true)
  const [scraping, setScraping] = useState(false)
  const [filter, setFilter] = useState('all') // 'all', '故障', 'メンテナンス'
  const [searchQuery, setSearchQuery] = useState('')
  const [notification, setNotification] = useState(null)
  const [scrapingProgress, setScrapingProgress] = useState([])
  const [showMap, setShowMap] = useState(false)
  const [mapMarkers, setMapMarkers] = useState([])
  const [geocodingProgress, setGeocodingProgress] = useState(0)

  // データを読み込む関数
  const loadData = async () => {
    try {
      setLoading(true)
      const response = await fetch('/data.json')
      if (response.ok) {
        const jsonData = await response.json()
        setData(jsonData)
        setFilteredData(jsonData)
      } else {
        console.error('データの読み込みに失敗しました')
        setData([])
        setFilteredData([])
      }
    } catch (error) {
      console.error('データの読み込みエラー:', error)
      setData([])
      setFilteredData([])
    } finally {
      setLoading(false)
    }
  }

  // 初期ロード
  useEffect(() => {
    loadData()
  }, [])

  // フィルタリングと検索
  useEffect(() => {
    let filtered = data

    // 種別でフィルタリング
    if (filter !== 'all') {
      filtered = filtered.filter(item => item['種別'] === filter)
    }

    // 検索クエリでフィルタリング
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(item => 
        item['施設名']?.toLowerCase().includes(query) ||
        item['住所']?.toLowerCase().includes(query) ||
        item['都道府県']?.toLowerCase().includes(query)
      )
    }

    setFilteredData(filtered)
  }, [data, filter, searchQuery])

  // サーバーの接続確認
  const checkServerConnection = async () => {
    try {
      const response = await fetch('http://localhost:8000/health', {
        method: 'GET',
        signal: AbortSignal.timeout(3000) // 3秒でタイムアウト
      })
      return response.ok
    } catch (error) {
      return false
    }
  }

  // スクレイピングを実行する関数（SSEでリアルタイム進捗を取得）
  const handleScrape = async () => {
    try {
      setScraping(true)
      setScrapingProgress([])
      
      // まずサーバーが起動しているか確認
      const serverAvailable = await checkServerConnection()
      if (!serverAvailable) {
        setNotification({
          type: 'error',
          message: 'FastAPIサーバーに接続できません。サーバーが起動しているか確認してください（http://localhost:8000）'
        })
        setScraping(false)
        setTimeout(() => {
          setNotification(null)
        }, 5000)
        return
      }

      // fetch APIを使ってSSEで進捗を取得
      const response = await fetch('http://localhost:8000/run-scrape', {
        method: 'POST',
        headers: {
          'Accept': 'text/event-stream',
        },
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        
        if (done) {
          console.log('SSEストリームが終了しました')
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          // 空行やコメント行をスキップ
          if (!line.trim() || line.startsWith(':')) {
            continue
          }
          
          if (line.startsWith('data: ')) {
            const message = line.slice(6).trim()
            console.log('受信したメッセージ:', message)
            
            if (message) {
              setScrapingProgress(prev => {
                const newProgress = [...prev, message]
                console.log('進捗更新:', newProgress.length, '件')
                return newProgress
              })
              
              // 完了メッセージをチェック
              if (message.includes('完了') || message.includes('done') || message.includes('スクレイピングが')) {
                setScraping(false)
                
                // 成功かエラーかを判定
                if (message.includes('エラー') || message.includes('error')) {
                  setNotification({
                    type: 'error',
                    message: 'データ収集中にエラーが発生しました'
                  })
                } else {
                  setNotification({
                    type: 'success',
                    message: 'データ収集が完了しました'
                  })
                  // 少し待ってからデータを再読み込み
                  setTimeout(() => {
                    loadData()
                  }, 1000)
                }
                
                // 5秒後に通知を消す
                setTimeout(() => {
                  setNotification(null)
                  setScrapingProgress([])
                }, 5000)
                return
              }
            }
          }
        }
      }

    } catch (error) {
      console.error('スクレイピングエラー:', error)
      setScraping(false)
      let errorMessage = 'サーバーに接続できませんでした'
      
      if (error.name === 'AbortError' || error.message.includes('Failed to fetch')) {
        errorMessage = 'FastAPIサーバーに接続できません。サーバーが起動しているか確認してください（http://localhost:8000）'
      } else if (error.message) {
        errorMessage = `エラー: ${error.message}`
      }
      
      setNotification({
        type: 'error',
        message: errorMessage
      })
      setTimeout(() => {
        setNotification(null)
        setScrapingProgress([])
      }, 5000)
    }
  }

  // Google MapsのURLを生成
  const getGoogleMapsUrl = (address) => {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`
  }

  // 住所を緯度・経度に変換
  const geocodeAddress = async (address) => {
    try {
      const response = await fetch('http://localhost:8000/geocode', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ address }),
      })
      const data = await response.json()
      if (data.success) {
        return { lat: data.lat, lon: data.lon, display_name: data.display_name }
      }
      return null
    } catch (error) {
      console.error('ジオコーディングエラー:', error)
      return null
    }
  }

  // 地図マーカーを生成
  const generateMapMarkers = async () => {
    if (filteredData.length === 0) {
      setMapMarkers([])
      return
    }

    setGeocodingProgress(0)
    const markers = []
    
    // バッチ処理でジオコーディング（レート制限を考慮）
    for (let i = 0; i < filteredData.length; i++) {
      const item = filteredData[i]
      const address = item['住所'] || item['都道府県'] || item['施設名']
      
      if (address && address.length > 3) {
        const coords = await geocodeAddress(address)
        if (coords) {
          markers.push({
            id: i,
            position: [coords.lat, coords.lon],
            facility: item['施設名'],
            address: item['住所'],
            status: item['種別'],
            detail: item['詳細内容'],
            updateDate: item['更新日'],
          })
        }
      }
      
      setGeocodingProgress(Math.round(((i + 1) / filteredData.length) * 100))
      
      // レート制限を考慮して1秒待機
      if (i < filteredData.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
    }
    
    setMapMarkers(markers)
  }

  // 地図表示を切り替え
  useEffect(() => {
    if (showMap && filteredData.length > 0 && mapMarkers.length === 0) {
      generateMapMarkers()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMap])

  // 地図の中心座標を計算
  const mapCenter = useMemo(() => {
    if (mapMarkers.length === 0) {
      return [35.6812, 139.7671] // 東京駅の座標（デフォルト）
    }
    
    const lats = mapMarkers.map(m => m.position[0])
    const lons = mapMarkers.map(m => m.position[1])
    
    return [
      (Math.max(...lats) + Math.min(...lats)) / 2,
      (Math.max(...lons) + Math.min(...lons)) / 2,
    ]
  }, [mapMarkers])

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ヘッダー */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">
              EV充電器ステータス・ダッシュボード
            </h1>
            <button
              onClick={handleScrape}
              disabled={scraping}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors shadow-md hover:shadow-lg"
            >
              {scraping ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>収集しています...</span>
                </>
              ) : (
                <>
                  <RefreshCw className="w-5 h-5" />
                  <span>最新データを取得</span>
                </>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* 通知 */}
      {notification && (
        <div className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-4`}>
          <div className={`p-4 rounded-lg ${
            notification.type === 'success' 
              ? 'bg-green-100 text-green-800 border border-green-300' 
              : 'bg-red-100 text-red-800 border border-red-300'
          }`}>
            <div className="flex items-center gap-2">
              {notification.type === 'success' ? (
                <span className="text-green-600">✓</span>
              ) : (
                <AlertCircle className="w-5 h-5" />
              )}
              <span>{notification.message}</span>
            </div>
          </div>
        </div>
      )}

      {/* スクレイピング進捗表示 */}
      {scraping && scrapingProgress.length > 0 && (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
              <h3 className="font-semibold text-blue-900">スクレイピング進捗</h3>
            </div>
            <div className="bg-white rounded border border-blue-200 p-3 max-h-64 overflow-y-auto">
              <div className="space-y-1 font-mono text-sm">
                {scrapingProgress.map((line, index) => (
                  <div key={index} className="text-gray-700">
                    {line}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* フィルターと検索 */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* フィルタータブ */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setFilter('all')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              filter === 'all'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            すべて ({data.length})
          </button>
          <button
            onClick={() => setFilter('故障')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              filter === '故障'
                ? 'bg-red-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            故障のみ ({data.filter(item => item['種別'] === '故障').length})
          </button>
          <button
            onClick={() => setFilter('メンテナンス')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              filter === 'メンテナンス'
                ? 'bg-orange-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            メンテナンスのみ ({data.filter(item => item['種別'] === 'メンテナンス').length})
          </button>
        </div>

        {/* 検索バーと地図表示切り替え */}
        <div className="mb-6 space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="施設名、住所、都道府県で検索..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          
          {/* 地図表示切り替えボタン */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setShowMap(!showMap)
                if (!showMap && filteredData.length > 0 && mapMarkers.length === 0) {
                  generateMapMarkers()
                }
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                showMap
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-100 border border-gray-300'
              }`}
            >
              <MapPin className="w-5 h-5" />
              {showMap ? 'リスト表示' : '地図表示'}
            </button>
            {showMap && geocodingProgress > 0 && geocodingProgress < 100 && (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>位置情報を取得中... {geocodingProgress}%</span>
              </div>
            )}
          </div>
        </div>

        {/* 地図表示 */}
        {showMap && (
          <div className="mb-6">
            <div className="bg-white rounded-lg shadow-md overflow-hidden" style={{ height: '600px' }}>
              <MapContainer
                center={mapCenter}
                zoom={mapMarkers.length > 0 ? 6 : 5}
                style={{ height: '100%', width: '100%' }}
              >
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                {mapMarkers.map((marker) => (
                  <Marker key={marker.id} position={marker.position}>
                    <Popup>
                      <div className="p-2">
                        <h3 className="font-bold text-lg mb-2">{marker.facility}</h3>
                        <p className="text-sm text-gray-600 mb-1">
                          <span className={`inline-block px-2 py-1 rounded text-xs ${
                            marker.status === '故障' ? 'bg-red-100 text-red-800' : 'bg-orange-100 text-orange-800'
                          }`}>
                            {marker.status}
                          </span>
                        </p>
                        {marker.address && (
                          <p className="text-sm text-gray-600 mb-1">📍 {marker.address}</p>
                        )}
                        {marker.updateDate && (
                          <p className="text-xs text-gray-500 mb-2">更新: {marker.updateDate}</p>
                        )}
                        {marker.detail && (
                          <p className="text-sm text-gray-700 mt-2">{marker.detail.substring(0, 100)}...</p>
                        )}
                      </div>
                    </Popup>
                  </Marker>
                ))}
              </MapContainer>
            </div>
            {mapMarkers.length > 0 && (
              <p className="text-sm text-gray-600 mt-2">
                地図上に {mapMarkers.length}件の施設を表示中
              </p>
            )}
          </div>
        )}

        {/* データ表示 */}
        {loading ? (
          <div className="flex justify-center items-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            <span className="ml-3 text-gray-600">データを読み込み中...</span>
          </div>
        ) : filteredData.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-gray-500 text-lg">データがありません</p>
            <p className="text-gray-400 text-sm mt-2">
              {searchQuery || filter !== 'all' 
                ? '検索条件を変更してください' 
                : '「最新データを取得」ボタンをクリックしてデータを収集してください'}
            </p>
          </div>
        ) : (
          <>
            {!showMap && (
              <>
                <div className="mb-4 text-sm text-gray-600">
                  表示中: {filteredData.length}件 / 全{data.length}件
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredData.map((item, index) => (
                <div
                  key={index}
                  className={`bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow p-5 border-l-4 ${
                    item['種別'] === '故障' ? 'border-red-500' : 'border-orange-500'
                  }`}
                >
                  {/* ヘッダー */}
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="text-lg font-bold text-gray-900 flex-1">
                      {item['施設名'] || '施設名不明'}
                    </h3>
                    <span
                      className={`px-2 py-1 rounded text-xs font-semibold whitespace-nowrap ml-2 ${
                        item['種別'] === '故障'
                          ? 'bg-red-100 text-red-800'
                          : 'bg-orange-100 text-orange-800'
                      }`}
                    >
                      {item['種別'] === '故障' ? (
                        <span className="flex items-center gap-1">
                          <AlertCircle className="w-3 h-3" />
                          故障
                        </span>
                      ) : (
                        <span className="flex items-center gap-1">
                          <Wrench className="w-3 h-3" />
                          メンテナンス
                        </span>
                      )}
                    </span>
                  </div>

                  {/* 詳細内容 */}
                  {item['詳細内容'] && (
                    <p className="text-sm text-gray-600 mb-3 line-clamp-2">
                      {item['詳細内容']}
                    </p>
                  )}

                  {/* 住所 */}
                  {item['住所'] && (
                    <div className="flex items-start gap-2 mb-3">
                      <MapPin className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                      <a
                        href={getGoogleMapsUrl(item['住所'])}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-blue-600 hover:text-blue-800 hover:underline flex-1"
                      >
                        {item['住所']}
                      </a>
                    </div>
                  )}

                  {/* 更新日 */}
                  {item['更新日'] && (
                    <div className="flex items-center gap-2 mb-3 text-sm text-gray-500">
                      <Calendar className="w-4 h-4" />
                      <span>{item['更新日']}</span>
                    </div>
                  )}

                  {/* バッジ */}
                  <div className="flex flex-wrap gap-2 mt-4">
                    {item['出力'] && (
                      <span className="flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                        <Zap className="w-3 h-3" />
                        {item['出力']}
                      </span>
                    )}
                    {item['充電タイプ'] && (
                      <span className="px-2 py-1 bg-gray-100 text-gray-800 rounded text-xs font-medium">
                        {item['充電タイプ']}
                      </span>
                    )}
                    {item['メーカー'] && (
                      <span className="px-2 py-1 bg-gray-100 text-gray-800 rounded text-xs font-medium">
                        {item['メーカー']}
                      </span>
                    )}
                    {item['充電器数'] && (
                      <span className="px-2 py-1 bg-gray-100 text-gray-800 rounded text-xs font-medium">
                        {item['充電器数']}台
                      </span>
                    )}
                  </div>

                  {/* 詳細URL */}
                  {item['詳細URL'] && (
                    <a
                      href={item['詳細URL']}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-3 inline-block text-sm text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      詳細を見る →
                    </a>
                  )}
                </div>
              ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default App
