#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
随机电影推荐器 - Web API 接口
为前端提供RESTful API接口
"""
import os
import json
import random
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# 导入项目模块
try:
    from main import ApiClient, Requester, load_or_fetch, pick_random_movie, recommend_batch
    from src.storage import list_favorites, save_favorite, remove_favorite
    from src.preferences import load_preferences
    from src.utils import get_genre_map, filter_by_genre
except ImportError as e:
    print(f"导入错误: {e}")
    # 定义空函数作为fallback
    def load_or_fetch(*args, **kwargs):
        return {"results": []}
    def pick_random_movie(movies, **kwargs):
        return random.choice(movies) if movies else None
    def recommend_batch(movies, n=3, **kwargs):
        return movies[:n] if movies else []
    def list_favorites():
        return []
    def save_favorite(movie):
        return True
    def remove_favorite(movie_id):
        return True
    def load_preferences():
        return {}
    def get_genre_map(*args, **kwargs):
        return {}
    def filter_by_genre(movies, genre_id=None, genre_name=None):
        return movies

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 全局变量存储API客户端
api_client = None
requester = None
cached_movies = []

def initialize_api_client():
    """初始化API客户端"""
    global api_client, requester
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        print("警告: 未配置 TMDB_API_KEY 环境变量")
        return False
    
    try:
        api_client = ApiClient(
            base_url=os.getenv("TMDB_BASE_URL", "https://api.themoviedb.org/3"),
            api_key=api_key,
            key_type=os.getenv("TMDB_KEY_TYPE", "v3"),
            timeout=int(os.getenv("REQUEST_TIMEOUT", 30)),
            max_retries=int(os.getenv("MAX_RETRIES", 2))
        )
        requester = Requester(api_client)
        return True
    except Exception as e:
        print(f"初始化API客户端失败: {e}")
        return False

def load_movies():
    """加载电影数据"""
    global cached_movies
    try:
        if api_client is None:
            if not initialize_api_client():
                return False
        
        data = load_or_fetch(api_client, requester, force_fetch=False)
        if data and data.get("results"):
            cached_movies = data["results"]
            print(f"成功加载 {len(cached_movies)} 部电影")
            return True
        else:
            print("未能加载电影数据")
            return False
    except Exception as e:
        print(f"加载电影数据失败: {e}")
        cached_movies = []
        return False

@app.before_request
def before_request():
    """在每个请求之前检查并初始化"""
    global api_client, cached_movies
    if api_client is None:
        initialize_api_client()
    if not cached_movies:
        load_movies()

@app.route('/')
def serve_index():
    """提供前端页面"""
    return send_from_directory('.', 'index.html')

@app.route('/api/genres')
def get_genres():
    """获取电影类型列表"""
    try:
        if api_client is None:
            return jsonify({
                'success': False,
                'error': 'API客户端未初始化'
            }), 500
            
        language = request.args.get('language', 'zh-CN')
        result = api_client.get_genres(language)
        
        if result.get('success') and result.get('data'):
            return jsonify({
                'success': True,
                'data': result['data']
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '获取类型失败')
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        }), 500

@app.route('/api/random')
def get_random_movie():
    """获取随机电影推荐"""
    try:
        genre_id = request.args.get('genre_id')
        if genre_id:
            try:
                genre_id = int(genre_id)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': '无效的类型ID'
                }), 400
        
        preferences = load_preferences()
        
        # 过滤电影
        filtered_movies = cached_movies
        if genre_id:
            filtered_movies = filter_by_genre(cached_movies, genre_id=genre_id)
            if not filtered_movies:
                filtered_movies = cached_movies
        
        if not filtered_movies:
            return jsonify({
                'success': False,
                'error': '没有可用的电影数据'
            }), 404
        
        # 选择随机电影
        movie = pick_random_movie(filtered_movies, preferences=preferences)
        if not movie:
            movie = random.choice(filtered_movies)
        
        # 添加类型名称
        try:
            genre_map = get_genre_map(api_client, language='zh-CN') or {}
            if 'genre_ids' in movie:
                movie['genre_names'] = [genre_map.get(str(gid)) for gid in movie['genre_ids'] if genre_map.get(str(gid))]
        except:
            movie['genre_names'] = []
        
        return jsonify({
            'success': True,
            'movie': movie
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取随机电影失败: {str(e)}'
        }), 500

@app.route('/api/batch')
def get_batch_recommendation():
    """获取批量电影推荐"""
    try:
        count = int(request.args.get('count', 3))
        genre_id = request.args.get('genre_id')
        if genre_id:
            try:
                genre_id = int(genre_id)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': '无效的类型ID'
                }), 400
        
        preferences = load_preferences()
        
        # 过滤电影
        filtered_movies = cached_movies
        if genre_id:
            filtered_movies = filter_by_genre(cached_movies, genre_id=genre_id)
            if not filtered_movies:
                filtered_movies = cached_movies
        
        if not filtered_movies:
            return jsonify({
                'success': False,
                'error': '没有可用的电影数据'
            }), 404
        
        # 批量推荐
        movies = recommend_batch(
            filtered_movies, 
            n=count, 
            preferences=preferences,
            diversify_by=preferences.get('diversify_by', 'genre')
        )
        
        # 添加类型名称
        try:
            genre_map = get_genre_map(api_client, language='zh-CN') or {}
            for movie in movies:
                if 'genre_ids' in movie:
                    movie['genre_names'] = [genre_map.get(str(gid)) for gid in movie['genre_ids'] if genre_map.get(str(gid))]
        except:
            for movie in movies:
                movie['genre_names'] = []
        
        return jsonify({
            'success': True,
            'movies': movies
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取批量推荐失败: {str(e)}'
        }), 500

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """刷新电影数据"""
    try:
        global cached_movies
        if api_client is None:
            if not initialize_api_client():
                return jsonify({
                    'success': False,
                    'error': 'API客户端初始化失败'
                }), 500
        
        data = load_or_fetch(api_client, requester, force_fetch=True)
        if data and data.get("results"):
            cached_movies = data["results"]
            return jsonify({
                'success': True,
                'message': f'成功刷新 {len(cached_movies)} 部电影数据'
            })
        else:
            return jsonify({
                'success': False,
                'error': '刷新数据失败'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'刷新数据失败: {str(e)}'
        }), 500

@app.route('/api/favorites', methods=['GET'])
def get_favorites():
    """获取收藏列表"""
    try:
        favorites = list_favorites()
        return jsonify({
            'success': True,
            'favorites': favorites
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取收藏失败: {str(e)}'
        }), 500

@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    """添加收藏"""
    try:
        data = request.get_json()
        movie_id = data.get('movie_id')
        
        if not movie_id:
            return jsonify({
                'success': False,
                'error': '缺少电影ID'
            }), 400
        
        # 从缓存中查找电影
        movie = next((m for m in cached_movies if m.get('id') == movie_id), None)
        if not movie:
            return jsonify({
                'success': False,
                'error': '电影未找到'
            }), 404
        
        # 保存收藏
        success = save_favorite(movie)
        if success:
            return jsonify({
                'success': True,
                'message': '收藏成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '收藏失败'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'添加收藏失败: {str(e)}'
        }), 500

@app.route('/api/favorites', methods=['DELETE'])
def delete_favorite():
    """删除收藏"""
    try:
        data = request.get_json()
        movie_id = data.get('movie_id')
        
        if not movie_id:
            return jsonify({
                'success': False,
                'error': '缺少电影ID'
            }), 400
        
        # 删除收藏
        success = remove_favorite(movie_id)
        if success:
            return jsonify({
                'success': True,
                'message': '删除收藏成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '删除收藏失败或收藏不存在'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'删除收藏失败: {str(e)}'
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': '接口不存在'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': '服务器内部错误'
    }), 500

if __name__ == '__main__':
    # 确保数据目录存在
    os.makedirs('data', exist_ok=True)
    
    # 启动Flask应用
    print("🚀 启动随机电影推荐器Web服务...")
    print("📝 请确保已设置 TMDB_API_KEY 环境变量")
    print("🌐 访问 http://localhost:5000 使用前端界面")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
