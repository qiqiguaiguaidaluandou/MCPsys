import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
// TODO(T2): uncomment after styles are created
// import './styles/main.scss';

const app = createApp(App);
app.use(createPinia());
app.mount('#app');
