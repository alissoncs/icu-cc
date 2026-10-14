import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { t } from "./i18n";
import FormScreen from "./screens/FormScreen";
import ActivitiesScreen from "./screens/ActivitiesScreen";
import ActivityScreen from "./screens/ActivityScreen";
import WeekScreen from "./screens/WeekScreen";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">{t.app}</strong>
        <nav aria-label={t.navLabel}>
          <NavLink to="/" end>
            {t.nav.form}
          </NavLink>
          <NavLink to="/atividades">{t.nav.activities}</NavLink>
          <NavLink to="/semana">{t.nav.week}</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<FormScreen />} />
          <Route path="/atividades" element={<ActivitiesScreen />} />
          <Route path="/atividades/:id" element={<ActivityScreen />} />
          <Route path="/semana/:date?" element={<WeekScreen />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
